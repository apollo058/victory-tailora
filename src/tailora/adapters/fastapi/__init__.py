"""FastAPI 연결을 제공하는 어댑터 모듈."""

from typing import Any

from fastapi import FastAPI

from tailora.adapters.fastapi.middleware import TailoraMiddleware
from tailora.core.policies import RedactionPolicy
from tailora.core.store import RingBuffer


def enable_inspector(
    app: FastAPI,
    store: RingBuffer | None = None,
    policy: RedactionPolicy | None = None,
    engine: object | None = None,
    excluded_paths: tuple[str, ...] = ("/__tailora",),
) -> RingBuffer:
    """FastAPI 애플리케이션에 Tailora 미들웨어 및 쿼리 수집기를 활성화한다."""
    resolved_store = store if store is not None else RingBuffer()
    app.add_middleware(
        TailoraMiddleware,
        store=resolved_store,
        policy=policy,
        enabled=True,
        excluded_paths=excluded_paths,
    )
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
    return resolved_store


def __getattr__(name: str) -> Any:
    """선택적 의존성인 SQLAlchemy 관련 함수를 지연 임포트한다."""
    if name in ("register_sqlalchemy_inspector", "unregister_sqlalchemy_inspector"):
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
    "enable_inspector",
    "register_sqlalchemy_inspector",
    "unregister_sqlalchemy_inspector",
]
