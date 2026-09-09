"""요청 이벤트와 쿼리 이벤트의 기본 동작을 확인한다."""

from datetime import datetime, timezone

import pytest

from tailora.core.enums import Framework
from tailora.core.events import ErrorSummary, QueryEvent, RequestEvent


def make_query(sequence: int, duration_ms: float) -> QueryEvent:
    """테스트용 쿼리 이벤트를 만든다."""
    return QueryEvent(
        query_id=f"q-{sequence}",
        sequence=sequence,
        started_at=datetime(2026, 8, 13, 10, 20, 30, tzinfo=timezone.utc),
        duration_ms=duration_ms,
        statement="SELECT * FROM users WHERE id = ?",
        fingerprint="select users by id",
        database="default",
    )


def test_request_event_calculates_query_summary():
    """요청 이벤트가 쿼리 개수와 전체 쿼리 시간을 계산하는지 확인한다."""
    first_query = make_query(1, 4.1)
    second_query = make_query(2, 4.3)

    event = RequestEvent(
        request_id="req-1",
        timestamp=datetime(2026, 8, 13, 10, 20, 30, tzinfo=timezone.utc),
        framework=Framework.FASTAPI,
        method="get",
        route_template="/users/{user_id}",
        status_code=200,
        duration_ms=42.7,
        queries=[first_query, second_query],
    )

    assert event.framework == "fastapi"
    assert event.method == "GET"
    assert event.query_count == 2
    assert event.query_time_ms == pytest.approx(8.4)
    assert event.total_query_count == 2
    assert event.total_query_time_ms == pytest.approx(8.4)
    assert event.is_queries_truncated is False
    assert event.queries == [first_query, second_query]


def test_request_event_preserves_total_query_metadata_for_partial_list():
    """일부 쿼리만 보관해도 전체 실행 횟수와 시간을 보존한다."""
    query = make_query(1, 4.1)

    event = RequestEvent(
        request_id="req-truncated",
        timestamp=datetime(2026, 8, 13, 10, 20, 30, tzinfo=timezone.utc),
        framework="fastapi",
        method="GET",
        route_template="/users",
        status_code=200,
        duration_ms=20.0,
        queries=[query],
        total_query_count=3,
        total_query_time_ms=12.5,
    )

    assert event.query_count == 1
    assert event.total_query_count == 3
    assert event.total_query_time_ms == 12.5
    assert event.is_queries_truncated is True


def test_request_event_supports_request_without_queries():
    """쿼리가 없는 요청을 빈 목록과 0초의 집계값으로 표현하는지 확인한다."""
    event = RequestEvent(
        request_id="req-no-query",
        timestamp=datetime(2026, 8, 13, 10, 20, 30, tzinfo=timezone.utc),
        framework="fastapi",
        method="GET",
        route_template="/health",
        status_code=200,
        duration_ms=1.2,
    )

    assert event.queries == []
    assert event.query_count == 0
    assert event.query_time_ms == 0.0


def test_error_summary_can_be_attached_to_request_and_query():
    """요청과 쿼리에 안전한 오류 요약을 연결할 수 있는지 확인한다."""
    error = ErrorSummary(
        type="DatabaseError",
        message="database operation failed",
        stack_hint="repository.py:42",
    )
    query = make_query(1, 2.0)
    query.error = error

    event = RequestEvent(
        request_id="req-error",
        timestamp=datetime(2026, 8, 13, 10, 20, 30, tzinfo=timezone.utc),
        framework="fastapi",
        method="POST",
        route_template="/users",
        status_code=500,
        duration_ms=10.0,
        queries=[query],
        error=error,
    )

    assert event.error == error
    assert event.queries[0].error == error
