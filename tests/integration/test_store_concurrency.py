"""RingBuffer의 동시 접근 동작을 확인한다."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from tailora.core.events import RequestEvent
from tailora.core.store import RingBuffer


EVENT_TIME = datetime(2026, 8, 13, 10, 20, 30, tzinfo=timezone.utc)


def make_event(sequence: int) -> RequestEvent:
    """테스트용 요청 이벤트를 만든다."""
    return RequestEvent(
        request_id=f"req-{sequence}",
        timestamp=EVENT_TIME,
        framework="fastapi",
        method="GET",
        route_template="/health",
        status_code=200,
        duration_ms=1.0,
    )


def test_concurrent_additions_keep_capacity_and_index_consistent():
    """동시에 이벤트를 추가해도 용량과 색인이 일치하는지 확인한다."""
    store = RingBuffer(capacity=32)
    events = [make_event(sequence) for sequence in range(200)]

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(store.add, events))

    snapshots = store.list()
    request_ids = {event.request_id for event in snapshots}

    assert len(snapshots) == 32
    assert len(request_ids) == 32
    assert all(store.get(request_id) is not None for request_id in request_ids)
    assert store.size() == len(request_ids)


def test_concurrent_add_and_read_do_not_break_store():
    """이벤트 추가와 조회를 동시에 해도 예외 없이 일관성을 유지하는지 확인한다."""
    store = RingBuffer(capacity=64)

    def add_and_read(event: RequestEvent) -> list[RequestEvent]:
        """이벤트를 추가하고 최신 목록을 읽는다."""
        store.add(event)
        return store.list(limit=1)

    events = [make_event(sequence) for sequence in range(1000, 1100)]
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(add_and_read, events))

    assert all(len(result) == 1 for result in results)
    assert store.size() == 64
    assert len(store.list()) == 64
