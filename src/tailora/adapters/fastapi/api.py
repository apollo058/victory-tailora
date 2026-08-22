"""Inspector 데이터를 조회할 수 있는 FastAPI APIRouter를 제공한다."""

from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Path, Query, params
from fastapi.responses import JSONResponse

from tailora.core.aggregation import compute_aggregates
from tailora.core.events import RequestEvent
from tailora.core.policies import RedactionPolicy
from tailora.core.privacy import redact_event
from tailora.core.serialization import request_event_to_dict
from tailora.core.store import RingBuffer


def _summarize_request(event: RequestEvent) -> dict[str, Any]:
    """요청 이벤트에서 목록 표시에 필요한 요약 정보만 추출한다."""
    error_summary = None
    if event.error is not None:
        error_summary = {
            "type": event.error.type,
            "message": event.error.message,
            "stack_hint": event.error.stack_hint,
        }

    return {
        "request_id": event.request_id,
        "timestamp": event.timestamp.isoformat().replace("+00:00", "Z"),
        "framework": event.framework,
        "method": event.method,
        "route_template": event.route_template,
        "status_code": event.status_code,
        "duration_ms": event.duration_ms,
        "query_count": event.query_count,
        "query_time_ms": event.query_time_ms,
        "error": error_summary,
    }


def create_inspector_router(
    store: RingBuffer,
    prefix: str = "/__tailora",
    policy: RedactionPolicy | None = None,
    dependencies: Sequence[params.Depends] | None = None,
) -> APIRouter:
    """지정된 저장소를 읽는 Inspector 전용 APIRouter를 생성한다."""
    resolved_policy = policy if policy is not None else RedactionPolicy()
    router = APIRouter(
        prefix=prefix,
        tags=["Tailora Inspector"],
        dependencies=dependencies,
    )

    @router.get("/health")
    def health_check() -> dict[str, Any]:
        """Inspector 활성 상태와 저장소 용량 메타데이터를 반환한다."""
        return {
            "status": "ok",
            "stored_requests": store.size(),
            "capacity": store.capacity,
        }

    @router.get("/requests")
    def list_requests(
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, Any]:
        """최근 요청 이벤트 목록을 마스킹 적용 후 최신순으로 반환한다."""
        events = store.list(limit=limit)
        redacted_events = [redact_event(ev, resolved_policy) for ev in events]
        items = [_summarize_request(ev) for ev in redacted_events]
        return {
            "items": items,
            "count": len(items),
            "limit": limit,
        }

    @router.get("/requests/{request_id}")
    def get_request_detail(
        request_id: str = Path(..., description="조회할 요청 ID"),
    ) -> Any:
        """단일 요청 이벤트와 연결된 쿼리 전체를 마스킹하여 반환한다."""
        event = store.get(request_id)
        if event is None:
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "request_not_found",
                        "message": (
                            f"Request event '{request_id}' was not found"
                        ),
                    },
                },
            )
        redacted_event = redact_event(event, resolved_policy)
        return request_event_to_dict(redacted_event)

    @router.get("/aggregates")
    def get_aggregates() -> dict[str, Any]:
        """현재 저장된 이벤트의 경로 및 Fingerprint 집계 결과를 반환한다."""
        events = store.list()
        redacted_events = [redact_event(ev, resolved_policy) for ev in events]
        return compute_aggregates(redacted_events)

    return router
