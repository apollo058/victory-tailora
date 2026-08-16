"""RingBuffer 저장소의 기본 동작을 확인한다."""

from datetime import datetime, timezone

import pytest

from tailora.core.events import QueryEvent, RequestEvent
from tailora.core.store import RingBuffer


EVENT_TIME = datetime(2026, 8, 13, 10, 20, 30, tzinfo=timezone.utc)


def make_query(sequence: int = 1) -> QueryEvent:
    """테스트용 쿼리 이벤트를 만든다."""
    return QueryEvent(
        query_id=f"q-{sequence}",
        sequence=sequence,
        started_at=EVENT_TIME,
        duration_ms=1.0,
        statement="SELECT * FROM users WHERE id = 1",
    )


def make_event(
    request_id: str,
    queries: list[QueryEvent] | None = None,
) -> RequestEvent:
    """테스트용 요청 이벤트를 만든다."""
    return RequestEvent(
        request_id=request_id,
        timestamp=EVENT_TIME,
        framework="fastapi",
        method="GET",
        route_template="/users",
        status_code=200,
        duration_ms=10.0,
        queries=queries or [],
    )


def test_default_capacity_is_100():
    """기본 저장 용량이 100개인지 확인한다."""
    store = RingBuffer()

    assert store.capacity == 100
    assert store.size() == 0


@pytest.mark.parametrize("capacity", [0, -1, True, "100", 10_001])
def test_capacity_rejects_invalid_values(capacity):
    """잘못된 저장 용량을 거부하는지 확인한다."""
    with pytest.raises(ValueError, match="capacity"):
        RingBuffer(capacity=capacity)


def test_add_requires_request_event():
    """RequestEvent가 아닌 값은 추가할 수 없는지 확인한다."""
    store = RingBuffer()

    with pytest.raises(TypeError, match="RequestEvent"):
        store.add("not an event")


def test_add_and_get_return_independent_snapshots():
    """저장·조회 결과가 외부 변경과 분리되는지 확인한다."""
    event = make_event("req-1", queries=[make_query()])
    store = RingBuffer()

    store.add(event)
    event.route_template = "/changed"
    event.queries[0].statement = "SELECT secret"

    result = store.get("req-1")

    assert result is not None
    assert result is not event
    assert result.route_template == "/users"
    assert result.queries[0].statement == "SELECT * FROM users WHERE id = 1"

    result.route_template = "/also-changed"
    result.queries.append(make_query(2))
    result.queries[0].statement = "SELECT another-secret"

    stored_again = store.get("req-1")
    assert stored_again is not None
    assert stored_again.route_template == "/users"
    assert len(stored_again.queries) == 1
    assert stored_again.queries[0].statement == "SELECT * FROM users WHERE id = 1"


def test_capacity_evicts_oldest_event_and_index():
    """용량을 넘으면 가장 오래된 이벤트와 색인이 함께 제거되는지 확인한다."""
    store = RingBuffer(capacity=2)

    store.add(make_event("req-1"))
    store.add(make_event("req-2"))
    store.add(make_event("req-3"))

    assert store.size() == 2
    assert [event.request_id for event in store.list()] == ["req-3", "req-2"]
    assert store.get("req-1") is None
    assert store.get("req-2") is not None
    assert store.get("req-3") is not None


def test_list_returns_latest_first_and_applies_limit():
    """목록이 최신순이고 limit으로 개수를 줄일 수 있는지 확인한다."""
    store = RingBuffer(capacity=3)
    for index in range(1, 4):
        store.add(make_event(f"req-{index}"))

    assert [event.request_id for event in store.list()] == [
        "req-3",
        "req-2",
        "req-1",
    ]
    assert [event.request_id for event in store.list(limit=2)] == [
        "req-3",
        "req-2",
    ]
    assert [event.request_id for event in store.list(limit=10)] == [
        "req-3",
        "req-2",
        "req-1",
    ]


@pytest.mark.parametrize("limit", [0, -1, True, "2"])
def test_list_rejects_invalid_limit(limit):
    """잘못된 조회 개수 제한을 거부하는지 확인한다."""
    with pytest.raises(ValueError, match="limit"):
        RingBuffer().list(limit=limit)


def test_get_returns_none_for_unknown_request_id():
    """존재하지 않는 요청 ID는 None으로 반환하는지 확인한다."""
    assert RingBuffer().get("missing") is None


def test_get_rejects_empty_request_id():
    """비어 있는 요청 ID를 거부하는지 확인한다."""
    with pytest.raises(ValueError, match="request_id"):
        RingBuffer().get(" ")


def test_get_normalizes_request_id_whitespace():
    """요청 ID 앞뒤 공백을 제거한 뒤 조회하는지 확인한다."""
    store = RingBuffer()
    store.add(make_event(" req-1 "))

    result = store.get(" req-1 ")

    assert result is not None
    assert result.request_id == "req-1"


def test_duplicate_request_id_is_rejected():
    """같은 요청 ID를 두 번 저장하지 못하게 하는지 확인한다."""
    store = RingBuffer()
    store.add(make_event("req-1"))

    with pytest.raises(ValueError, match="request_id"):
        store.add(make_event("req-1"))

    assert store.size() == 1


def test_clear_removes_events_and_index():
    """clear가 이벤트와 ID 색인을 모두 비우는지 확인한다."""
    store = RingBuffer(capacity=2)
    store.add(make_event("req-1"))
    store.add(make_event("req-2"))

    store.clear()

    assert store.size() == 0
    assert store.list() == []
    assert store.get("req-1") is None
    assert store.get("req-2") is None

    store.add(make_event("req-3"))
    assert store.size() == 1


def test_capacity_is_read_only():
    """저장소 생성 후 capacity를 바꿀 수 없는지 확인한다."""
    store = RingBuffer(capacity=2)

    with pytest.raises(AttributeError):
        store.capacity = 3
