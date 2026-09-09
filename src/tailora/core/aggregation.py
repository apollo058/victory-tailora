"""저장된 요청 및 쿼리 이벤트의 기본 집계 기능을 제공한다."""

from collections import defaultdict
from typing import Any

from tailora.core.events import RequestEvent


def _aggregate_routes(events: list[RequestEvent]) -> list[dict[str, Any]]:
    """요청 이벤트 목록에서 라우트 템플릿별 지표를 집계한다."""
    route_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0,
            "total_duration": 0.0,
            "max_duration": 0.0,
            "total_queries": 0,
        },
    )

    for event in events:
        stats = route_stats[event.route_template]
        stats["count"] += 1
        stats["total_duration"] += event.duration_ms
        stats["max_duration"] = max(stats["max_duration"], event.duration_ms)
        stats["total_queries"] += event.total_query_count

    results: list[dict[str, Any]] = []
    for route, stats in route_stats.items():
        count = stats["count"]
        avg_duration = (
            round(stats["total_duration"] / count, 6) if count > 0 else 0.0
        )
        results.append(
            {
                "route_template": route,
                "count": count,
                "avg_duration_ms": avg_duration,
                "max_duration_ms": round(stats["max_duration"], 6),
                "total_queries": stats["total_queries"],
            },
        )

    return sorted(
        results,
        key=lambda item: (-item["count"], -item["avg_duration_ms"]),
    )


def _aggregate_fingerprints(
    events: list[RequestEvent],
) -> list[dict[str, Any]]:
    """요청 이벤트 목록에서 SQL Fingerprint별 지표를 집계한다."""
    fp_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "total_duration": 0.0, "request_ids": set()},
    )

    for event in events:
        for query in event.queries:
            if query.fingerprint is not None:
                stats = fp_stats[query.fingerprint]
                stats["count"] += 1
                stats["total_duration"] += query.duration_ms
                stats["request_ids"].add(event.request_id)

    results: list[dict[str, Any]] = []
    for fp, stats in fp_stats.items():
        count = stats["count"]
        total_duration = round(stats["total_duration"], 6)
        avg_duration = round(total_duration / count, 6) if count > 0 else 0.0
        results.append(
            {
                "fingerprint": fp,
                "count": count,
                "request_count": len(stats["request_ids"]),
                "total_duration_ms": total_duration,
                "avg_duration_ms": avg_duration,
            },
        )

    return sorted(
        results,
        key=lambda item: (-item["count"], -item["total_duration_ms"]),
    )


def compute_aggregates(events: list[RequestEvent]) -> dict[str, Any]:
    """저장된 이벤트 목록에서 라우트 및 Fingerprint 집계 결과를 생성한다."""
    if not events:
        return {"routes": [], "fingerprints": []}

    return {
        "routes": _aggregate_routes(events),
        "fingerprints": _aggregate_fingerprints(events),
    }
