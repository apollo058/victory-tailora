"""현재 요청의 수집 상태를 보관하고 관리하는 컨텍스트 모듈."""

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime
import math

from tailora.core.events import QueryEvent


def _require_text(value: object, field_name: str) -> str:
    """문자열 필드가 비어 있지 않은지 확인하고 앞뒤 공백을 제거한다."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _require_datetime(value: object, field_name: str) -> datetime:
    """시각 필드가 datetime 객체인지 확인한다."""
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    return value


def _require_finite_number(value: object, field_name: str) -> float:
    """숫자 필드가 유한한 숫자인지 확인한다."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


@dataclass
class RequestContext:
    """현재 진행 중인 HTTP 요청의 수집 상태를 보관한다."""

    request_id: str
    started_at: datetime
    start_perf: float
    queries: list[QueryEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        """컨텍스트 필드의 유효성을 검증한다."""
        self.request_id = _require_text(self.request_id, "request_id")
        self.started_at = _require_datetime(self.started_at, "started_at")
        self.start_perf = _require_finite_number(self.start_perf, "start_perf")
        if not isinstance(self.queries, list):
            raise ValueError("queries must be a list")


_CURRENT_CONTEXT: ContextVar[RequestContext | None] = ContextVar(
    "tailora_current_request_context",
    default=None,
)


def get_current_context() -> RequestContext | None:
    """현재 비동기 작업에 설정된 요청 컨텍스트를 반환한다."""
    return _CURRENT_CONTEXT.get()


def set_current_context(context: RequestContext) -> Token[RequestContext | None]:
    """현재 비동기 작업에 새 요청 컨텍스트를 설정하고 복원용 토큰을 반환한다."""
    if not isinstance(context, RequestContext):
        raise TypeError("context must be a RequestContext")
    return _CURRENT_CONTEXT.set(context)


def reset_current_context(token: Token[RequestContext | None]) -> None:
    """이전 토큰을 사용해 컨텍스트를 원래 상태로 되돌린다."""
    _CURRENT_CONTEXT.reset(token)


def record_query(query: QueryEvent) -> None:
    """현재 요청 컨텍스트에 실행된 쿼리 이벤트를 추가한다.

    현재 요청 컨텍스트가 없으면 아무 동작도 하지 않고 안전하게 건너뛴다.
    """
    if not isinstance(query, QueryEvent):
        return
    context = _CURRENT_CONTEXT.get()
    if context is not None:
        context.queries.append(query)

