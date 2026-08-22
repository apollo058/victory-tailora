"""요청 및 쿼리 이벤트의 느린 요청, 느린 쿼리, 중복 쿼리 신호를 분석한다."""

from collections import defaultdict
from typing import Any

from tailora.core.events import QueryEvent, RequestEvent
from tailora.core.policies import ThresholdPolicy


def _find_slow_queries(
    queries: list[QueryEvent],
    threshold_ms: float | None,
) -> list[int]:
    """개별 실행 시간이 임계값 이상인 쿼리의 sequence 목록을 반환한다."""
    if threshold_ms is None:
        return []
    return [q.sequence for q in queries if q.duration_ms >= threshold_ms]


def _find_duplicate_queries(
    queries: list[QueryEvent],
    threshold_count: int | None,
) -> list[dict[str, Any]]:
    """동일 요청 내에서 중복 실행된 SQL Fingerprint 목록을 반환한다."""
    if threshold_count is None:
        return []

    fp_sequences: dict[str, list[int]] = defaultdict(list)
    for q in queries:
        if q.fingerprint is not None:
            fp_sequences[q.fingerprint].append(q.sequence)

    duplicates: list[dict[str, Any]] = []
    for fp, seqs in fp_sequences.items():
        if len(seqs) >= threshold_count:
            duplicates.append(
                {
                    "fingerprint": fp,
                    "count": len(seqs),
                    "sequences": seqs,
                },
            )

    return sorted(duplicates, key=lambda item: -item["count"])


def _check_query_heavy(
    query_count: int,
    query_time_ms: float,
    count_limit: int | None,
    time_limit_ms: float | None,
) -> tuple[bool, list[str]]:
    """쿼리 개수 또는 총 실행 시간이 임계값을 초과했는지 판정한다."""
    reasons: list[str] = []
    if count_limit is not None and query_count >= count_limit:
        reasons.append("count")
    if time_limit_ms is not None and query_time_ms >= time_limit_ms:
        reasons.append("time")
    return len(reasons) > 0, reasons


def analyze_request_signals(
    event: RequestEvent,
    policy: ThresholdPolicy | None = None,
) -> dict[str, Any]:
    """요청 이벤트의 상세 진단 신호 및 메타데이터를 계산한다."""
    resolved_policy = policy if policy is not None else ThresholdPolicy()

    slow_request = (
        resolved_policy.slow_request_ms is not None
        and event.duration_ms >= resolved_policy.slow_request_ms
    )
    slow_queries = _find_slow_queries(
        event.queries,
        resolved_policy.slow_query_ms,
    )
    duplicate_queries = _find_duplicate_queries(
        event.queries,
        resolved_policy.duplicate_query_threshold,
    )
    is_heavy, heavy_reasons = _check_query_heavy(
        event.query_count,
        event.query_time_ms,
        resolved_policy.query_heavy_count,
        resolved_policy.query_heavy_time_ms,
    )

    applied_thresholds = {
        "slow_request_ms": resolved_policy.slow_request_ms,
        "slow_query_ms": resolved_policy.slow_query_ms,
        "duplicate_query_threshold": (
            resolved_policy.duplicate_query_threshold
        ),
        "query_heavy_count": resolved_policy.query_heavy_count,
        "query_heavy_time_ms": resolved_policy.query_heavy_time_ms,
    }

    return {
        "slow_request": slow_request,
        "slow_queries": slow_queries,
        "duplicate_queries": duplicate_queries,
        "query_heavy": is_heavy,
        "query_heavy_reasons": heavy_reasons,
        "applied_thresholds": applied_thresholds,
        "analyzed_query_count": len(event.queries),
        "total_query_count": event.query_count,
        "is_queries_truncated": len(event.queries) < event.query_count,
    }


def summarize_request_signals(
    event: RequestEvent,
    policy: ThresholdPolicy | None = None,
) -> dict[str, Any]:
    """목록 표시를 위한 경량 신호 요약 객체를 생성한다."""
    signals = analyze_request_signals(event, policy)
    return {
        "slow_request": signals["slow_request"],
        "has_slow_query": len(signals["slow_queries"]) > 0,
        "has_duplicate_query": len(signals["duplicate_queries"]) > 0,
        "query_heavy": signals["query_heavy"],
    }
