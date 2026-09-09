"""FastAPI 연결을 제공하는 어댑터 모듈."""

from collections.abc import Sequence
from dataclasses import dataclass
import logging
from typing import Any

from fastapi import FastAPI, params
from starlette.routing import Match

from tailora.adapters.fastapi.api import create_inspector_router
from tailora.adapters.fastapi.docs import (
    get_docs_excluded_paths,
    install_tailora_docs,
)
from tailora.adapters.fastapi.middleware import TailoraMiddleware
from tailora.adapters.fastapi.security import normalize_inspector_dependencies
from tailora.config import AccessCheck, InspectorConfig
from tailora.core.policies import RedactionPolicy, ThresholdPolicy
from tailora.core.store import DEFAULT_CAPACITY, RingBuffer

_STATE_ENABLED_KEY = "_tailora_inspector_enabled"
_STATE_STORE_KEY = "_tailora_inspector_store"
_STATE_REGISTRATION_KEY = "_tailora_inspector_registration"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _RegistrationState:
    """한 FastAPI 앱에 완료된 Inspector 등록 정보를 보관한다."""

    config: InspectorConfig
    store: RingBuffer
    engine: object | None
    dependencies: tuple[params.Depends, ...]


@dataclass(frozen=True)
class _ApplicationSnapshot:
    """Inspector 등록 실패 시 복구할 FastAPI 내부 상태를 보관한다."""

    routes: list[Any]
    middleware: list[Any]
    middleware_stack: Any


def _build_config(
    *,
    enabled: bool,
    environment: str,
    allow_in_production: bool,
    prefix: str,
    store_capacity: int,
    api_default_limit: int,
    api_max_limit: int,
    policy: RedactionPolicy | None,
    threshold_policy: ThresholdPolicy | None,
    access_check: AccessCheck | None,
    excluded_paths: tuple[str, ...] | None,
) -> InspectorConfig:
    """FastAPI 활성화 인자를 검증된 통합 설정으로 만든다."""
    return InspectorConfig(
        enabled=enabled,
        environment=environment,
        allow_in_production=allow_in_production,
        path_prefix=prefix,
        store_capacity=store_capacity,
        api_default_limit=api_default_limit,
        api_max_limit=api_max_limit,
        redaction_policy=policy if policy is not None else RedactionPolicy(),
        threshold_policy=(
            threshold_policy
            if threshold_policy is not None
            else ThresholdPolicy()
        ),
        access_check=access_check,
        excluded_paths=(
            excluded_paths if excluded_paths is not None else ()
        ),
    )


def _get_existing_registration(
    app: FastAPI,
    config: InspectorConfig,
    store: RingBuffer | None,
    engine: object | None,
    dependencies: tuple[params.Depends, ...],
) -> RingBuffer | None:
    """같은 등록은 재사용하고 다른 설정의 중복 등록은 거부한다."""
    state = getattr(app.state, _STATE_REGISTRATION_KEY, None)
    if state is None:
        return None
    is_same = (
        isinstance(state, _RegistrationState)
        and state.config == config
        and (store is None or state.store is store)
        and state.engine is engine
        and state.dependencies == dependencies
    )
    if not is_same:
        raise ValueError(
            "Inspector is already enabled with a different configuration",
        )
    return state.store


def _route_accepts_path(route: Any, path: str) -> bool:
    """FastAPI 라우트가 주어진 GET 경로를 가로채는지 확인한다."""
    matcher = getattr(route, "matches", None)
    if not callable(matcher):
        return False
    scope = {
        "type": "http",
        "path": path,
        "root_path": "",
        "method": "GET",
        "scheme": "http",
        "query_string": b"",
        "headers": [],
    }
    try:
        match, _ = matcher(scope)
    except Exception:
        return False
    return match in {Match.FULL, Match.PARTIAL}


def _ensure_prefix_is_available(app: FastAPI, prefix: str) -> None:
    """Inspector prefix 아래에 기존 FastAPI 라우트가 없는지 확인한다."""
    probe_paths = (prefix, f"{prefix}/health")
    for route in app.router.routes:
        path = getattr(route, "path", None)
        if isinstance(path, str) and (
            path == prefix or path.startswith(f"{prefix}/")
        ):
            raise ValueError(
                f"path_prefix conflicts with an existing route: {prefix}",
            )
        if any(_route_accepts_path(route, probe) for probe in probe_paths):
            raise ValueError(
                f"path_prefix conflicts with an existing route: {prefix}",
            )


def _merge_excluded_paths(
    app: FastAPI,
    config: InspectorConfig,
) -> tuple[str, ...]:
    """사용자 경로에 Inspector와 문서 경로를 항상 추가한다."""
    system_paths = (config.path_prefix, *get_docs_excluded_paths(app))
    return tuple(dict.fromkeys((*config.excluded_paths, *system_paths)))


def _snapshot_application(app: FastAPI) -> _ApplicationSnapshot:
    """부분 등록 실패에 대비해 FastAPI 라우트와 미들웨어를 복사한다."""
    return _ApplicationSnapshot(
        routes=list(app.router.routes),
        middleware=list(app.user_middleware),
        middleware_stack=app.middleware_stack,
    )


def _restore_application(app: FastAPI, snapshot: _ApplicationSnapshot) -> None:
    """FastAPI 앱을 Inspector 등록 전 상태로 복구한다."""
    app.router.routes[:] = snapshot.routes
    app.user_middleware[:] = snapshot.middleware
    app.middleware_stack = snapshot.middleware_stack


def _register_engine(engine: object) -> None:
    """선택적 SQLAlchemy 의존성을 지연 import하고 Engine hook을 등록한다."""
    try:
        from tailora.adapters.fastapi.sqlalchemy import (
            register_sqlalchemy_inspector,
        )
    except ImportError as error:
        raise ImportError(
            "SQLAlchemy is required to inspect database engines. "
            "Install it with: pip install 'tailora[sqlalchemy]'",
        ) from error
    register_sqlalchemy_inspector(engine)  # type: ignore[arg-type]


def _register_components(
    app: FastAPI,
    config: InspectorConfig,
    store: RingBuffer,
    engine: object | None,
    dependencies: tuple[params.Depends, ...],
) -> None:
    """검증된 설정으로 미들웨어·API·문서·SQL hook을 등록한다."""
    app.add_middleware(
        TailoraMiddleware,
        store=store,
        policy=config.redaction_policy,
        enabled=True,
        excluded_paths=_merge_excluded_paths(app, config),
    )
    router = create_inspector_router(
        store=store,
        prefix=config.path_prefix,
        policy=config.redaction_policy,
        threshold_policy=config.threshold_policy,
        dependencies=dependencies,
        access_check=config.access_check,
        default_limit=config.api_default_limit,
        max_limit=config.api_max_limit,
    )
    app.include_router(router)
    install_tailora_docs(
        app,
        inspector_prefix=config.path_prefix,
        access_check=config.access_check,
    )
    if engine is not None:
        _register_engine(engine)


def _record_registration(
    app: FastAPI,
    config: InspectorConfig,
    store: RingBuffer,
    engine: object | None,
    dependencies: tuple[params.Depends, ...],
) -> None:
    """모든 구성 요소가 성공한 뒤에만 앱의 활성 상태를 기록한다."""
    state = _RegistrationState(config, store, engine, dependencies)
    setattr(app.state, _STATE_ENABLED_KEY, True)
    setattr(app.state, _STATE_STORE_KEY, store)
    setattr(app.state, _STATE_REGISTRATION_KEY, state)


def _log_enabled_config(config: InspectorConfig) -> None:
    """민감한 값 없이 Inspector 활성화 범위와 경고를 기록한다."""
    logger.info(
        "Tailora Inspector enabled environment=%s path=%s capacity=%d access_check=%s",
        config.environment,
        config.path_prefix,
        config.store_capacity,
        config.access_check is not None,
    )
    if config.is_production:
        logger.warning(
            "Tailora Inspector is enabled in production; restrict network access",
        )
    if config.access_check is None:
        logger.warning(
            "Tailora Inspector has no access check; bind the app to a trusted network",
        )


def _resolve_capacity(
    store: RingBuffer | None,
    store_capacity: int | None,
) -> int:
    """명시한 용량, 주입된 저장소, 기본값 순으로 저장 용량을 정한다."""
    if store_capacity is not None:
        return store_capacity
    if store is not None:
        return store.capacity
    return DEFAULT_CAPACITY


def _resolve_path_prefix(
    prefix: str | None,
    path_prefix: str,
) -> str:
    """기존 prefix 인자와 새 path_prefix 인자를 하나의 경로로 합친다."""
    if prefix is None:
        return path_prefix
    if path_prefix != "/__tailora" and path_prefix != prefix:
        raise ValueError("prefix and path_prefix must refer to the same path")
    return prefix


def _enable_with_config(
    app: FastAPI,
    config: InspectorConfig,
    store: RingBuffer | None,
    engine: object | None,
    dependencies: tuple[params.Depends, ...],
) -> RingBuffer:
    """검증된 설정을 사용해 FastAPI 앱에 Inspector를 원자적으로 등록한다."""
    existing = _get_existing_registration(
        app,
        config,
        store,
        engine,
        dependencies,
    )
    if existing is not None:
        return existing
    resolved_store = store or RingBuffer(config.store_capacity)
    if not config.enabled:
        return resolved_store
    if resolved_store.capacity != config.store_capacity:
        raise ValueError("store_capacity must match the provided store capacity")
    _ensure_prefix_is_available(app, config.path_prefix)
    snapshot = _snapshot_application(app)
    try:
        _register_components(app, config, resolved_store, engine, dependencies)
    except Exception:
        _restore_application(app, snapshot)
        raise
    _record_registration(app, config, resolved_store, engine, dependencies)
    _log_enabled_config(config)
    return resolved_store


def enable_inspector(
    app: FastAPI,
    store: RingBuffer | None = None,
    policy: RedactionPolicy | None = None,
    threshold_policy: ThresholdPolicy | None = None,
    engine: object | None = None,
    prefix: str | None = None,
    excluded_paths: tuple[str, ...] | None = None,
    dependencies: Sequence[params.Depends] | None = None,
    *,
    enabled: bool = False,
    environment: str = "development",
    allow_in_production: bool = False,
    access_check: AccessCheck | None = None,
    path_prefix: str = "/__tailora",
    store_capacity: int | None = None,
    api_default_limit: int = 20,
    api_max_limit: int = 100,
) -> RingBuffer:
    """명시적으로 켜진 FastAPI 앱에만 Tailora Inspector를 원자적으로 등록한다."""
    resolved_capacity = _resolve_capacity(store, store_capacity)
    resolved_dependencies = normalize_inspector_dependencies(dependencies)
    config = _build_config(
        enabled=enabled,
        environment=environment,
        allow_in_production=allow_in_production,
        prefix=_resolve_path_prefix(prefix, path_prefix),
        store_capacity=resolved_capacity,
        api_default_limit=api_default_limit,
        api_max_limit=api_max_limit,
        policy=policy,
        threshold_policy=threshold_policy,
        access_check=access_check,
        excluded_paths=excluded_paths,
    )
    return _enable_with_config(
        app,
        config,
        store,
        engine,
        resolved_dependencies,
    )


def __getattr__(name: str) -> Any:
    """선택적 의존성인 SQLAlchemy 관련 함수를 지연 임포트한다."""
    if name in (
        "register_sqlalchemy_inspector",
        "unregister_sqlalchemy_inspector",
    ):
        try:
            import tailora.adapters.fastapi.sqlalchemy as sqla_module

            return getattr(sqla_module, name)
        except ImportError as error:
            raise ImportError(
                f"{name} requires SQLAlchemy. "
                "Install it with: pip install 'tailora[sqlalchemy]'",
            ) from error
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "TailoraMiddleware",
    "create_inspector_router",
    "enable_inspector",
    "register_sqlalchemy_inspector",
    "unregister_sqlalchemy_inspector",
]
