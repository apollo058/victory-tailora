"""Inspector API 응답 데이터를 화면 ViewModel로 변환하고 정규화하는 모듈."""

from typing import Any


def transform_request_summary(item: dict[str, Any]) -> dict[str, Any]:
    """목록 조회용 개별 요청 요약 딕셔너리를 화면 표시용 뷰모델로 변환한다."""
    signals = item.get("signals") or {}
    duration_ms = float(item.get("duration_ms", 0.0))
    query_time_ms = float(item.get("query_time_ms", 0.0))

    return {
        "request_id": str(item.get("request_id", "")),
        "method": str(item.get("method", "GET")).upper(),
        "route_template": str(item.get("route_template", "/")),
        "status_code": int(item.get("status_code", 200)),
        "duration_ms": duration_ms,
        "query_count": int(item.get("query_count", 0)),
        "query_time_ms": query_time_ms,
        "is_slow": bool(signals.get("slow_request", False)),
        "has_dup": bool(signals.get("has_duplicate_query", False)),
        "has_slow_query": bool(signals.get("has_slow_query", False)),
        "is_heavy": bool(signals.get("query_heavy", False)),
    }


def transform_request_detail(detail: dict[str, Any]) -> dict[str, Any]:
    """상세 조회용 요청 딕셔너리를 화면 상세 뷰모델로 변환한다."""
    signals = detail.get("signals") or {}
    applied_thresholds = signals.get("applied_thresholds") or {}
    raw_queries = detail.get("queries") or []

    slow_seqs = set(signals.get("slow_queries") or [])
    transformed_queries = []
    for q in raw_queries:
        seq = int(q.get("sequence", 0))
        transformed_queries.append(
            {
                "sequence": seq,
                "duration_ms": float(q.get("duration_ms", 0.0)),
                "database": str(q.get("database", "db")),
                "statement": str(q.get("statement", "")),
                "fingerprint": q.get("fingerprint"),
                "is_slow": seq in slow_seqs,
            }
        )

    return {
        "request_id": str(detail.get("request_id", "")),
        "timestamp": detail.get("timestamp"),
        "framework": str(detail.get("framework", "fastapi")),
        "method": str(detail.get("method", "GET")).upper(),
        "route_template": str(detail.get("route_template", "/")),
        "status_code": int(detail.get("status_code", 200)),
        "duration_ms": float(detail.get("duration_ms", 0.0)),
        "query_count": int(detail.get("query_count", 0)),
        "query_time_ms": float(detail.get("query_time_ms", 0.0)),
        "error": detail.get("error"),
        "slow_request_threshold_ms": applied_thresholds.get("slow_request_ms"),
        "slow_query_threshold_ms": applied_thresholds.get("slow_query_ms"),
        "is_slow_request": bool(signals.get("slow_request", False)),
        "slow_queries": signals.get("slow_queries") or [],
        "duplicate_queries": signals.get("duplicate_queries") or [],
        "query_heavy": bool(signals.get("query_heavy", False)),
        "query_heavy_reasons": signals.get("query_heavy_reasons") or [],
        "queries": transformed_queries,
    }
