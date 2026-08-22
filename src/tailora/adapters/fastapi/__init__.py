"""FastAPI 연결을 제공하는 어댑터 모듈."""

from fastapi import FastAPI

from tailora.adapters.fastapi.middleware import TailoraMiddleware
from tailora.core.policies import RedactionPolicy
from tailora.core.store import RingBuffer


def enable_inspector(
    app: FastAPI,
    store: RingBuffer | None = None,
    policy: RedactionPolicy | None = None,
    excluded_paths: tuple[str, ...] = ("/__tailora",),
) -> RingBuffer:
    """FastAPI 애플리케이션에 Tailora 미들웨어를 활성화하고 저장소를 반환한다."""
    resolved_store = store if store is not None else RingBuffer()
    app.add_middleware(
        TailoraMiddleware,
        store=resolved_store,
        policy=policy,
        enabled=True,
        excluded_paths=excluded_paths,
    )
    return resolved_store


__all__ = ["TailoraMiddleware", "enable_inspector"]
