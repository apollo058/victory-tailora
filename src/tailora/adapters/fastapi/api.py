"""Inspector 데이터를 조회할 수 있는 FastAPI APIRouter를 제공한다."""

from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Path, Query, params
from fastapi.responses import JSONResponse

from tailora.core.aggregation import compute_aggregates
from tailora.core.analysis import (
    analyze_request_signals,
    summarize_request_signals,
)
from tailora.core.events import RequestEvent
from tailora.core.policies import RedactionPolicy, ThresholdPolicy
from tailora.core.privacy import redact_event
from tailora.core.serialization import request_event_to_dict
from tailora.core.store import RingBuffer


def _summarize_request(
    event: RequestEvent,
    threshold_policy: ThresholdPolicy,
) -> dict[str, Any]:
    """요청 이벤트에서 목록 표시에 필요한 요약 정보와 신호 요약을 추출한다."""
    error_summary = None
    if event.error is not None:
        error_summary = {
            "type": event.error.type,
            "message": event.error.message,
            "stack_hint": event.error.stack_hint,
        }

    signals = summarize_request_signals(event, threshold_policy)

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
        "signals": signals,
    }


def create_inspector_router(
    store: RingBuffer,
    prefix: str = "/__tailora",
    policy: RedactionPolicy | None = None,
    threshold_policy: ThresholdPolicy | None = None,
    dependencies: Sequence[params.Depends] | None = None,
) -> APIRouter:
    """지정된 저장소를 읽는 Inspector 전용 APIRouter를 생성한다."""
    resolved_policy = policy if policy is not None else RedactionPolicy()
    resolved_thresholds = (
        threshold_policy
        if threshold_policy is not None
        else ThresholdPolicy()
    )

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
        """최근 요청 이벤트 목록을 마스킹 및 신호 분석 후 최신순으로 반환한다."""
        events = store.list(limit=limit)
        redacted_events = [redact_event(ev, resolved_policy) for ev in events]
        items = [
            _summarize_request(ev, resolved_thresholds)
            for ev in redacted_events
        ]
        return {
            "items": items,
            "count": len(items),
            "limit": limit,
            "thresholds": {
                "slow_request_ms": resolved_thresholds.slow_request_ms,
                "slow_query_ms": resolved_thresholds.slow_query_ms,
                "duplicate_query_threshold": (
                    resolved_thresholds.duplicate_query_threshold
                ),
                "query_heavy_count": (
                    resolved_thresholds.query_heavy_count
                ),
                "query_heavy_time_ms": (
                    resolved_thresholds.query_heavy_time_ms
                ),
            },
        }

    @router.get("/requests/{request_id}")
    def get_request_detail(
        request_id: str = Path(..., description="조회할 요청 ID"),
    ) -> Any:
        """단일 요청 이벤트와 연결된 쿼리 및 상세 신호 분석 결과를 반환한다."""
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
        result = request_event_to_dict(redacted_event)
        result["signals"] = analyze_request_signals(
            redacted_event,
            resolved_thresholds,
        )
        return result

    @router.get("/aggregates")
    def get_aggregates() -> dict[str, Any]:
        """현재 저장된 이벤트의 경로 및 Fingerprint 집계 결과와 임계값을 반환한다."""
        events = store.list()
        redacted_events = [redact_event(ev, resolved_policy) for ev in events]
        aggregates = compute_aggregates(redacted_events)
        aggregates["total_stored_requests"] = len(events)
        aggregates["thresholds"] = {
            "slow_request_ms": resolved_thresholds.slow_request_ms,
            "slow_query_ms": resolved_thresholds.slow_query_ms,
            "duplicate_query_threshold": (
                resolved_thresholds.duplicate_query_threshold
            ),
            "query_heavy_count": resolved_thresholds.query_heavy_count,
            "query_heavy_time_ms": resolved_thresholds.query_heavy_time_ms,
        }
        return aggregates

    @router.get("", include_in_schema=False)
    @router.get("/", include_in_schema=False)
    def inspector_ui_index() -> Any:
        """독립형 Inspector 웹 화면 HTML을 반환한다."""
        from fastapi.responses import Response

        from tailora.ui.loader import get_inspector_asset

        content, content_type = get_inspector_asset("index.html", base_path=prefix)
        return Response(content=content, media_type=content_type)

    @router.get("/{asset_name:path}", include_in_schema=False)
    def inspector_ui_asset(asset_name: str) -> Any:
        """독립형 Inspector 정적 자산(CSS, JS 등)을 반환한다."""
        from fastapi.responses import Response

        from tailora.ui.loader import get_inspector_asset

        try:
            content, content_type = get_inspector_asset(
                asset_name,
                base_path=prefix,
            )
            return Response(content=content, media_type=content_type)
        except FileNotFoundError:
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "asset_not_found",
                        "message": "Requested static asset was not found.",
                    },
                },
            )

    return router

