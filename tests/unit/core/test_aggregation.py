"""코어 집계 기능의 동작을 확인한다."""

from datetime import datetime, timezone

from tailora.core.aggregation import compute_aggregates
from tailora.core.events import QueryEvent, RequestEvent

EVENT_TIME = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)


def make_query(
    sequence: int,
    duration_ms: float,
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
    request_id: str,
    route_template: str,
    duration_ms: float,
    queries: list[QueryEvent] | None = None,
) -> RequestEvent:
    """테스트용 요청 이벤트를 생성한다."""
    return RequestEvent(
        request_id=request_id,
        timestamp=EVENT_TIME,
        framework="fastapi",
        method="GET",
        route_template=route_template,
        status_code=200,
        duration_ms=duration_ms,
        queries=queries or [],
    )


def test_compute_aggregates_empty_events():
    """이벤트가 없을 때 빈 집계 결과를 반환하는지 확인한다."""
    result = compute_aggregates([])

    assert result == {"routes": [], "fingerprints": []}


def test_compute_aggregates_route_metrics():
    """라우트 템플릿별 요청 수, 소요 시간, 쿼리 수가 정확히 집계되는지 확인한다."""
    q1 = make_query(1, 2.0)
    q2 = make_query(1, 3.0)
    q3 = make_query(2, 4.0)

    events = [
        make_request("r1", "/users/{id}", 10.0, [q1]),
        make_request("r2", "/users/{id}", 30.0, [q2, q3]),
        make_request("r3", "/health", 5.0, []),
    ]

    result = compute_aggregates(events)
    routes = {item["route_template"]: item for item in result["routes"]}

    assert len(routes) == 2

    users_metric = routes["/users/{id}"]
    assert users_metric["count"] == 2
    assert users_metric["avg_duration_ms"] == 20.0
    assert users_metric["max_duration_ms"] == 30.0
    assert users_metric["total_queries"] == 3

    health_metric = routes["/health"]
    assert health_metric["count"] == 1
    assert health_metric["avg_duration_ms"] == 5.0
    assert health_metric["max_duration_ms"] == 5.0
    assert health_metric["total_queries"] == 0


def test_compute_aggregates_fingerprint_metrics():
    """SQL Fingerprint별 실행 횟수와 실행 시간이 정확히 집계되는지 확인한다."""
    fp1 = "select * from users where id = ?"
    fp2 = "insert into users values (?, ?)"

    q1 = make_query(1, 2.0, fingerprint=fp1)
    q2 = make_query(2, 4.0, fingerprint=fp1)
    q3 = make_query(1, 10.0, fingerprint=fp2)

    events = [
        make_request("r1", "/users/{id}", 10.0, [q1, q2]),
        make_request("r2", "/users", 15.0, [q3]),
    ]

    result = compute_aggregates(events)
    fps = {item["fingerprint"]: item for item in result["fingerprints"]}

    assert len(fps) == 2

    fp1_metric = fps[fp1]
    assert fp1_metric["count"] == 2
    assert fp1_metric["request_count"] == 1
    assert fp1_metric["total_duration_ms"] == 6.0
    assert fp1_metric["avg_duration_ms"] == 3.0

    fp2_metric = fps[fp2]
    assert fp2_metric["count"] == 1
    assert fp2_metric["request_count"] == 1
    assert fp2_metric["total_duration_ms"] == 10.0
    assert fp2_metric["avg_duration_ms"] == 10.0


def test_compute_aggregates_queries_without_fingerprint():
    """fingerprint가 None인 쿼리가 있을 때도 정상 집계되는지 확인한다."""
    q = make_query(1, 2.0, fingerprint=None)
    events = [make_request("r1", "/test", 5.0, [q])]

    result = compute_aggregates(events)

    assert len(result["routes"]) == 1
    assert len(result["fingerprints"]) == 0

