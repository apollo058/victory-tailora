"""FastAPI 연결을 제공하는 어댑터 모듈."""

from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, params

from tailora.adapters.fastapi.api import create_inspector_router
from tailora.adapters.fastapi.middleware import TailoraMiddleware
from tailora.core.policies import RedactionPolicy
from tailora.core.store import RingBuffer

_STATE_ENABLED_KEY = "_tailora_inspector_enabled"
_STATE_STORE_KEY = "_tailora_inspector_store"


def enable_inspector(
    app: FastAPI,
    store: RingBuffer | None = None,
    policy: RedactionPolicy | None = None,
    engine: object | None = None,
    prefix: str = "/__tailora",
    excluded_paths: tuple[str, ...] | None = None,
    dependencies: Sequence[params.Depends] | None = None,
) -> RingBuffer:
    """FastAPI 앱에 Tailora 미들웨어, Inspector API, 쿼리 수집기를 활성화한다."""
    if getattr(app.state, _STATE_ENABLED_KEY, False):
        existing_store = getattr(app.state, _STATE_STORE_KEY, None)
        if isinstance(existing_store, RingBuffer):
            return existing_store

    resolved_store = store if store is not None else RingBuffer()

    # 사용자가 커스텀 제외 경로를 지정해도 시스템 prefix는 항상 포함
    user_paths = list(excluded_paths) if excluded_paths is not None else []
    merged_paths = tuple(dict.fromkeys(user_paths + [prefix]))

    app.add_middleware(
        TailoraMiddleware,
        store=resolved_store,
        policy=policy,
        enabled=True,
        excluded_paths=merged_paths,
    )

    router = create_inspector_router(
        store=resolved_store,
        prefix=prefix,
        policy=policy,
        dependencies=dependencies,
    )
    app.include_router(router)

    if engine is not None:
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

    setattr(app.state, _STATE_ENABLED_KEY, True)
    setattr(app.state, _STATE_STORE_KEY, resolved_store)

    return resolved_store


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
