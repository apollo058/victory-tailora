"""최근 요청 이벤트를 프로세스 메모리에 제한적으로 보관한다."""

from collections import deque
import copy
from threading import RLock

from tailora.core.events import RequestEvent


DEFAULT_CAPACITY = 100
MAX_CAPACITY = 10_000


def _validate_positive_integer(
    value: object,
    field_name: str,
    maximum: int | None = None,
) -> int:
    """값이 양의 정수이고 정해진 상한을 넘지 않는지 확인한다."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")
    if maximum is not None and value > maximum:
        raise ValueError(f"{field_name} must be at most {maximum}")
    return value


def _validate_request_id(value: object) -> str:
    """요청 ID가 비어 있지 않은 문자열인지 확인한다."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("request_id must be a non-empty string")
    return value


class RingBuffer:
    """최근 요청 이벤트만 정해진 개수만큼 보관하는 저장소."""

    def __init__(self, capacity: int = DEFAULT_CAPACITY) -> None:
        """저장 용량을 정하고 빈 저장소를 만든다."""
        self._capacity = _validate_positive_integer(
            capacity,
            "capacity",
            maximum=MAX_CAPACITY,
        )
        self._events: deque[RequestEvent] = deque()
        self._events_by_request_id: dict[str, RequestEvent] = {}
        self._lock = RLock()

    @property
    def capacity(self) -> int:
        """저장소가 보관할 수 있는 최대 이벤트 수를 반환한다."""
        return self._capacity

    def add(self, event: RequestEvent) -> None:
        """이벤트를 저장하고 용량을 넘으면 가장 오래된 이벤트를 지운다."""
        if not isinstance(event, RequestEvent):
            raise TypeError("event must be a RequestEvent")

        snapshot = copy.deepcopy(event)
        with self._lock:
            request_id = snapshot.request_id
            if request_id in self._events_by_request_id:
                raise ValueError("request_id already exists")
            self._events.append(snapshot)
            self._events_by_request_id[request_id] = snapshot
            if len(self._events) > self._capacity:
                evicted = self._events.popleft()
                del self._events_by_request_id[evicted.request_id]

    def list(self, limit: int | None = None) -> list[RequestEvent]:
        """최신 이벤트부터 복사본 목록을 반환한다."""
        if limit is None:
            item_limit = self._capacity
        else:
            item_limit = _validate_positive_integer(limit, "limit")
            item_limit = min(item_limit, self._capacity)

        with self._lock:
            events = list(self._events)
        latest_events = list(reversed(events))[:item_limit]
        return copy.deepcopy(latest_events)

    def get(self, request_id: str) -> RequestEvent | None:
        """요청 ID에 맞는 이벤트 복사본을 반환하고 없으면 None을 반환한다."""
        request_id = _validate_request_id(request_id)
        with self._lock:
            event = self._events_by_request_id.get(request_id)
        if event is None:
            return None
        return copy.deepcopy(event)

    def clear(self) -> None:
        """저장된 이벤트와 요청 ID 색인을 모두 비운다."""
        with self._lock:
            self._events.clear()
            self._events_by_request_id.clear()

    def size(self) -> int:
        """현재 저장된 이벤트 개수를 반환한다."""
        with self._lock:
            return len(self._events)
