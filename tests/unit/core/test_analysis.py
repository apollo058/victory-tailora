"""신호 분석 모듈(analysis.py)의 동작을 검증한다."""

from datetime import datetime, timezone

from tailora.core.analysis import (
    analyze_request_signals,
    summarize_request_signals,
)
from tailora.core.events import QueryEvent, RequestEvent
from tailora.core.policies import ThresholdPolicy

EVENT_TIME = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)


def make_query(
    sequence: int = 1,
    duration_ms: float = 10.0,
    fingerprint: str | None = "select 1",
) -> QueryEvent:
    """테스트용 쿼리 이벤트를 생성한다."""
    return QueryEvent(
        query_id=f"q-{sequence}",
        sequence=sequence,
        started_at=EVENT_TIME,
        duration_ms=duration_ms,
        statement="SELECT 1",
        fingerprint=fingerprint,
        database="sqlite",
    )


def make_request(
    request_id: str = "req-1",
    duration_ms: float = 100.0,
    queries: list[QueryEvent] | None = None,
) -> RequestEvent:
    """테스트용 요청 이벤트를 생성한다."""
    return RequestEvent(
        request_id=request_id,
        timestamp=EVENT_TIME,
        framework="fastapi",
        method="GET",
        route_template="/users",
        status_code=200,
        duration_ms=duration_ms,
        queries=queries or [],
    )


def test_analyze_slow_request_boundary():
    """slow_request 임계값 경계(<, ==, >)에 따른 판정을 확인한다."""
    policy = ThresholdPolicy(slow_request_ms=500.0)

    # 500ms 미만 -> False
    req_fast = make_request(duration_ms=499.9)
    assert analyze_request_signals(req_fast, policy)["slow_request"] is False

    # 500ms 이상 (경계값 포함) -> True
    req_exact = make_request(duration_ms=500.0)
    assert analyze_request_signals(req_exact, policy)["slow_request"] is True

    # 500ms 초과 -> True
    req_slow = make_request(duration_ms=500.1)
    assert analyze_request_signals(req_slow, policy)["slow_request"] is True


def test_analyze_slow_queries():
    """개별 쿼리 소요 시간이 slow_query_ms 이상인 쿼리 목록을 추출한다."""
    policy = ThresholdPolicy(slow_query_ms=100.0)

    q1 = make_query(sequence=1, duration_ms=50.0)
    q2 = make_query(sequence=2, duration_ms=100.0)  # exact match
    q3 = make_query(sequence=3, duration_ms=150.0)

    req = make_request(queries=[q1, q2, q3])
    signals = analyze_request_signals(req, policy)

    assert signals["slow_queries"] == [2, 3]


def test_analyze_duplicate_queries():
    """동일 요청 내에서 중복 실행된 fingerprint 감지를 확인한다."""
    policy = ThresholdPolicy(duplicate_query_threshold=2)

    fp_dup = "select * from users where id = ?"
    fp_unique = "insert into users values (?, ?)"

    q1 = make_query(sequence=1, duration_ms=5.0, fingerprint=fp_dup)
    q2 = make_query(sequence=2, duration_ms=5.0, fingerprint=fp_unique)
    q3 = make_query(sequence=3, duration_ms=5.0, fingerprint=fp_dup)
    q4 = make_query(sequence=4, duration_ms=5.0, fingerprint=None)  # None 제외

    req = make_request(queries=[q1, q2, q3, q4])
    signals = analyze_request_signals(req, policy)

    dup_list = signals["duplicate_queries"]
    assert len(dup_list) == 1
    assert dup_list[0]["fingerprint"] == fp_dup
    assert dup_list[0]["count"] == 2
    assert dup_list[0]["sequences"] == [1, 3]


def test_analyze_query_heavy_reasons():
    """쿼리 개수 또는 시간 초과 시 query_heavy 이유를 확인한다."""
    policy = ThresholdPolicy(query_heavy_count=3, query_heavy_time_ms=100.0)

    # 1. 둘 다 미만
    req_normal = make_request(
        queries=[
            make_query(1, 10.0),
            make_query(2, 10.0),
        ],
    )
    sig_normal = analyze_request_signals(req_normal, policy)
    assert sig_normal["query_heavy"] is False
    assert sig_normal["query_heavy_reasons"] == []

    # 2. 개수만 초과 (3개, 30ms)
    req_count = make_request(
        queries=[
            make_query(1, 10.0),
            make_query(2, 10.0),
            make_query(3, 10.0),
        ],
    )
    sig_count = analyze_request_signals(req_count, policy)
    assert sig_count["query_heavy"] is True
    assert sig_count["query_heavy_reasons"] == ["count"]

    # 3. 시간만 초과 (2개, 120ms)
    req_time = make_request(
        queries=[
            make_query(1, 60.0),
            make_query(2, 60.0),
        ],
    )
    sig_time = analyze_request_signals(req_time, policy)
    assert sig_time["query_heavy"] is True
    assert sig_time["query_heavy_reasons"] == ["time"]

    # 4. 둘 다 초과 (3개, 150ms)
    req_both = make_request(
        queries=[
            make_query(1, 50.0),
            make_query(2, 50.0),
            make_query(3, 50.0),
        ],
    )
    sig_both = analyze_request_signals(req_both, policy)
    assert sig_both["query_heavy"] is True
    assert sig_both["query_heavy_reasons"] == ["count", "time"]


def test_analyze_disabled_signals_with_none():
    """임계값이 None으로 비활성화된 경우 신호가 감지되지 않는지 확인한다."""
    disabled_policy = ThresholdPolicy(
        slow_request_ms=None,
        slow_query_ms=None,
        duplicate_query_threshold=None,
        query_heavy_count=None,
        query_heavy_time_ms=None,
    )

    q1 = make_query(1, 500.0, fingerprint="select 1")
    q2 = make_query(2, 500.0, fingerprint="select 1")
    req = make_request(duration_ms=1000.0, queries=[q1, q2])

    signals = analyze_request_signals(req, disabled_policy)
    assert signals["slow_request"] is False
    assert signals["slow_queries"] == []
    assert signals["duplicate_queries"] == []
    assert signals["query_heavy"] is False
    assert signals["query_heavy_reasons"] == []


def test_analyze_signals_metadata_and_truncation():
    """분석 결과에 메타데이터 및 쿼리 잘림 여부가 올바르게 포함되는지 확인한다."""
    policy = ThresholdPolicy(slow_request_ms=300.0)
    q1 = make_query(1, 10.0)
    req = make_request(duration_ms=200.0, queries=[q1])

    signals = analyze_request_signals(req, policy)
    assert signals["applied_thresholds"]["slow_request_ms"] == 300.0
    assert signals["analyzed_query_count"] == 1
    assert signals["total_query_count"] == 1
    assert signals["is_queries_truncated"] is False


def test_summarize_request_signals():
    """목록용 경량 신호 요약 객체가 올바르게 생성되는지 확인한다."""
    policy = ThresholdPolicy(
        slow_request_ms=100.0,
        slow_query_ms=50.0,
        duplicate_query_threshold=2,
        query_heavy_count=2,
    )

    q1 = make_query(1, 60.0, fingerprint="select 1")
    q2 = make_query(2, 10.0, fingerprint="select 1")

    req = make_request(duration_ms=150.0, queries=[q1, q2])
    summary = summarize_request_signals(req, policy)

    assert summary == {
        "slow_request": True,
        "has_slow_query": True,
        "has_duplicate_query": True,
        "query_heavy": True,
    }


def test_analyze_request_without_queries():
    """쿼리가 없는 요청도 안전하게 기본 신호를 반환하는지 확인한다."""
    req = make_request(duration_ms=50.0, queries=[])
    signals = analyze_request_signals(req)

    assert signals["slow_request"] is False
    assert signals["slow_queries"] == []
    assert signals["duplicate_queries"] == []
    assert signals["query_heavy"] is False
    assert signals["query_heavy_reasons"] == []
