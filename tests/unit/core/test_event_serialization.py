"""이벤트의 JSON 직렬화와 역직렬화를 확인한다."""

from datetime import datetime, timezone

from tailora.core.events import ErrorSummary, QueryEvent, RequestEvent
from tailora.core.serialization import (
    request_event_from_dict,
    request_event_from_json,
    request_event_to_dict,
    request_event_to_json,
)


def make_event() -> RequestEvent:
    """직렬화 테스트용 요청 이벤트를 만든다."""
    query = QueryEvent(
        query_id="q-1",
        sequence=1,
        started_at=datetime(2026, 8, 13, 10, 20, 31, tzinfo=timezone.utc),
        duration_ms=4.1,
        statement="SELECT ...",
        fingerprint="select users by id",
        database="default",
        error=None,
    )
    return RequestEvent(
        request_id="req-1",
        timestamp=datetime(2026, 8, 13, 10, 20, 30, tzinfo=timezone.utc),
        framework="fastapi",
        method="GET",
        route_template="/users/{user_id}",
        status_code=200,
        duration_ms=42.7,
        queries=[query],
        error=None,
    )


def test_request_event_to_dict_uses_stable_json_fields():
    """이벤트를 문서에서 정한 필드 이름의 사전으로 바꾸는지 확인한다."""
    event = make_event()

    payload = request_event_to_dict(event)

    assert payload == {
        "request_id": "req-1",
        "timestamp": "2026-08-13T10:20:30Z",
        "framework": "fastapi",
        "method": "GET",
        "route_template": "/users/{user_id}",
        "status_code": 200,
        "duration_ms": 42.7,
        "query_count": 1,
        "query_time_ms": 4.1,
        "queries": [
            {
                "query_id": "q-1",
                "sequence": 1,
                "started_at": "2026-08-13T10:20:31Z",
                "duration_ms": 4.1,
                "statement": "SELECT ...",
                "fingerprint": "select users by id",
                "database": "default",
                "error": None,
            }
        ],
        "error": None,
    }


def test_request_event_json_round_trip_preserves_event():
    """이벤트를 JSON으로 바꾼 뒤 다시 읽어도 같은 값인지 확인한다."""
    event = make_event()

    restored = request_event_from_json(request_event_to_json(event))

    assert restored == event


def test_request_event_from_dict_accepts_null_queries():
    """쿼리 필드가 null이어도 쿼리 없는 요청으로 읽는지 확인한다."""
    payload = request_event_to_dict(make_event())
    payload["queries"] = None
    payload["query_count"] = 0
    payload["query_time_ms"] = 0.0

    restored = request_event_from_dict(payload)

    assert restored.queries == []
    assert restored.query_count == 0
    assert restored.query_time_ms == 0.0


def test_error_summary_is_serialized_as_a_safe_nested_object():
    """오류 요약이 정해진 중첩 객체로 직렬화되는지 확인한다."""
    event = make_event()
    event.error = ErrorSummary(
        type="ValueError",
        message="invalid value",
        stack_hint="handlers.py:10",
    )

    payload = request_event_to_dict(event)
    restored = request_event_from_dict(payload)

    assert payload["error"] == {
        "type": "ValueError",
        "message": "invalid value",
        "stack_hint": "handlers.py:10",
    }
    assert restored.error == event.error
