"""Inspector 데이터를 조회할 수 있는 FastAPI APIRouter를 제공한다."""

from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Depends, Path, Query, params
from fastapi.responses import JSONResponse, Response

from tailora.adapters.fastapi.security import (
    create_inspector_access_dependency,
    normalize_inspector_dependencies,
)
from tailora.config import AccessCheck, InspectorConfig
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


def _thresholds_to_dict(policy: ThresholdPolicy) -> dict[str, Any]:
    """적용된 신호 임계값을 API 응답용 사전으로 바꾼다."""
    return {
        "slow_request_ms": policy.slow_request_ms,
        "slow_query_ms": policy.slow_query_ms,
        "duplicate_query_threshold": policy.duplicate_query_threshold,
        "query_heavy_count": policy.query_heavy_count,
        "query_heavy_time_ms": policy.query_heavy_time_ms,
    }


def _analysis_scope(events: list[RequestEvent]) -> dict[str, Any]:
    """집계가 사용한 요청·쿼리 범위와 잘림 여부를 반환한다."""
    return {
        "request_count": len(events),
        "analyzed_query_count": sum(event.query_count for event in events),
        "total_query_count": sum(event.total_query_count for event in events),
        "is_queries_truncated": any(
            event.is_queries_truncated for event in events
        ),
    }


def _summarize_request(
    event: RequestEvent,
    threshold_policy: ThresholdPolicy,
) -> dict[str, Any]:
    """요청 이벤트에서 목록 표시에 필요한 요약과 신호를 추출한다."""
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
        "query_count": event.total_query_count,
        "query_time_ms": event.total_query_time_ms,
        "analyzed_query_count": event.query_count,
        "is_queries_truncated": event.is_queries_truncated,
        "error": error_summary,
        "signals": summarize_request_signals(event, threshold_policy),
    }


def _resolve_dependencies(
    dependencies: Sequence[params.Depends] | None,
    access_check: AccessCheck | None,
) -> list[params.Depends]:
    """사용자 dependency와 Inspector 접근 hook을 라우터 dependency로 합친다."""
    resolved = list(normalize_inspector_dependencies(dependencies))
    if access_check is not None:
        dependency = create_inspector_access_dependency(access_check)
        resolved.append(Depends(dependency))
    return resolved


def _add_health_route(router: APIRouter, store: RingBuffer) -> None:
    """Inspector 상태와 저장소 메타데이터 조회 route를 추가한다."""

    @router.get("/health")
    def health_check() -> dict[str, Any]:
        """Inspector 활성 상태와 저장소 용량 메타데이터를 반환한다."""
        return {
            "status": "ok",
            "stored_requests": store.size(),
            "capacity": store.capacity,
        }


def _add_list_route(
    router: APIRouter,
    store: RingBuffer,
    policy: RedactionPolicy,
    thresholds: ThresholdPolicy,
    default_limit: int,
    max_limit: int,
) -> None:
    """안전한 최근 요청 목록을 제한된 개수로 반환하는 route를 추가한다."""

    @router.get("/requests")
    def list_requests(
        limit: int = Query(default=default_limit, ge=1, le=max_limit),
    ) -> dict[str, Any]:
        """최근 요청을 마스킹·신호 분석 후 최신순으로 반환한다."""
        snapshot = store.list()
        selected = snapshot[:limit]
        redacted = [redact_event(event, policy) for event in selected]
        items = [_summarize_request(event, thresholds) for event in redacted]
        return {
            "items": items,
            "count": len(items),
            "limit": limit,
            "total_stored_requests": len(snapshot),
            "is_truncated": len(snapshot) > limit,
            "thresholds": _thresholds_to_dict(thresholds),
        }


def _add_detail_route(
    router: APIRouter,
    store: RingBuffer,
    policy: RedactionPolicy,
    thresholds: ThresholdPolicy,
) -> None:
    """한 요청의 안전한 상세 정보와 진단 신호 route를 추가한다."""

    @router.get("/requests/{request_id}")
    def get_request_detail(
        request_id: str = Path(..., description="조회할 요청 ID"),
    ) -> Any:
        """단일 요청과 연결된 쿼리·상세 신호를 반환한다."""
        try:
            event = store.get(request_id)
        except ValueError:
            event = None
        if event is None:
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "request_not_found",
                        "message": "Requested event was not found.",
                    },
                },
            )
        redacted_event = redact_event(event, policy)
        result = request_event_to_dict(redacted_event)
        result["signals"] = analyze_request_signals(
            redacted_event,
            thresholds,
        )
        return result


def _add_aggregate_route(
    router: APIRouter,
    store: RingBuffer,
    policy: RedactionPolicy,
    thresholds: ThresholdPolicy,
    default_limit: int,
    max_limit: int,
) -> None:
    """경로·Fingerprint 집계와 분석 범위를 반환하는 route를 추가한다."""

    @router.get("/aggregates")
    def get_aggregates(
        limit: int = Query(default=default_limit, ge=1, le=max_limit),
    ) -> dict[str, Any]:
        """저장된 이벤트의 경로·Fingerprint 집계와 임계값을 반환한다."""
        events = [redact_event(event, policy) for event in store.list()]
        aggregates = compute_aggregates(events)
        route_count = len(aggregates["routes"])
        fingerprint_count = len(aggregates["fingerprints"])
        aggregates["routes"] = aggregates["routes"][:limit]
        aggregates["fingerprints"] = aggregates["fingerprints"][:limit]
        aggregates["total_stored_requests"] = len(events)
        aggregates["analysis_scope"] = _analysis_scope(events)
        aggregates["limit"] = limit
        aggregates["is_routes_truncated"] = route_count > limit
        aggregates["is_fingerprints_truncated"] = fingerprint_count > limit
        aggregates["thresholds"] = _thresholds_to_dict(thresholds)
        return aggregates


def _add_ui_routes(router: APIRouter, prefix: str) -> None:
    """독립형 Inspector 화면과 정적 자산 route를 추가한다."""

    @router.get("", include_in_schema=False)
    @router.get("/", include_in_schema=False)
    def inspector_ui_index() -> Response:
        """독립형 Inspector 웹 화면 HTML을 반환한다."""
        from tailora.ui.loader import get_inspector_asset

        content, content_type = get_inspector_asset("index.html", base_path=prefix)
        return Response(content=content, media_type=content_type)

    @router.get("/{asset_name:path}", include_in_schema=False)
    def inspector_ui_asset(asset_name: str) -> Response:
        """독립형 Inspector 정적 자산을 반환한다."""
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


def _resolve_router_config(
    store: RingBuffer,
    prefix: str,
    policy: RedactionPolicy | None,
    threshold_policy: ThresholdPolicy | None,
    access_check: AccessCheck | None,
    default_limit: int,
    max_limit: int,
) -> InspectorConfig:
    """공개 라우터 입력을 공통 Inspector 설정으로 검증한다."""
    if not isinstance(store, RingBuffer):
        raise TypeError("store must be a RingBuffer")
    return InspectorConfig(
        path_prefix=prefix,
        store_capacity=store.capacity,
        api_default_limit=default_limit,
        api_max_limit=max_limit,
        redaction_policy=(
            policy if policy is not None else RedactionPolicy()
        ),
        threshold_policy=(
            threshold_policy
            if threshold_policy is not None
            else ThresholdPolicy()
        ),
        access_check=access_check,
    )


def create_inspector_router(
    store: RingBuffer,
    prefix: str = "/__tailora",
    policy: RedactionPolicy | None = None,
    threshold_policy: ThresholdPolicy | None = None,
    dependencies: Sequence[params.Depends] | None = None,
    access_check: AccessCheck | None = None,
    default_limit: int = 20,
    max_limit: int = 100,
) -> APIRouter:
    """지정된 저장소를 읽는 제한된 Inspector APIRouter를 생성한다."""
    config = _resolve_router_config(
        store,
        prefix,
        policy,
        threshold_policy,
        access_check,
        default_limit,
        max_limit,
    )
    router = APIRouter(
        prefix=config.path_prefix,
        tags=["Tailora Inspector"],
        dependencies=_resolve_dependencies(dependencies, config.access_check),
    )
    _add_health_route(router, store)
    _add_list_route(
        router,
        store,
        config.redaction_policy,
        config.threshold_policy,
        config.api_default_limit,
        config.api_max_limit,
    )
    _add_detail_route(
        router,
        store,
        config.redaction_policy,
        config.threshold_policy,
    )
    _add_aggregate_route(
        router,
        store,
        config.redaction_policy,
        config.threshold_policy,
        config.api_default_limit,
        config.api_max_limit,
    )
    _add_ui_routes(router, config.path_prefix)
    return router
