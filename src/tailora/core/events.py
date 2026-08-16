"""프레임워크와 데이터베이스에 독립적인 이벤트 모델을 제공한다."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from typing import Any

from tailora.core.enums import Framework


def _require_text(value: Any, field_name: str, optional: bool = False) -> str | None:
    """문자열 필드가 비어 있지 않은지 확인한다."""
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _normalize_datetime(value: Any, field_name: str) -> datetime:
    """timezone이 있는 시각을 UTC 시각으로 바꾼다."""
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include timezone information")
    return value.astimezone(timezone.utc)


def _validate_duration(value: Any) -> float:
    """기간이 0 이상인 유한한 숫자인지 확인한다."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("duration_ms must be a number")
    duration = float(value)
    if duration < 0 or not math.isfinite(duration):
        raise ValueError("duration_ms must be finite and non-negative")
    return duration


def _validate_sequence(value: Any) -> int:
    """쿼리 순서가 1 이상인 정수인지 확인한다."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("sequence must be a positive integer")
    return value


def _validate_status_code(value: Any) -> int:
    """상태 코드가 HTTP 상태 코드 범위인지 확인한다."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("status_code must be an integer between 100 and 599")
    if not 100 <= value <= 599:
        raise ValueError("status_code must be an integer between 100 and 599")
    return value


@dataclass
class ErrorSummary:
    """민감한 원문을 포함하지 않는 오류 요약을 나타낸다."""

    type: str
    message: str | None = None
    stack_hint: str | None = None

    def __post_init__(self) -> None:
        """오류 요약의 문자열 필드를 검증한다."""
        self.type = _require_text(self.type, "error.type")  # type: ignore[assignment]
        self.message = _require_text(
            self.message,
            "error.message",
            optional=True,
        )
        self.stack_hint = _require_text(
            self.stack_hint,
            "error.stack_hint",
            optional=True,
        )


@dataclass
class QueryEvent:
    """요청 중 한 번 실행된 SQL 쿼리를 나타낸다."""

    query_id: str
    sequence: int
    started_at: datetime
    duration_ms: float
    statement: str | None = None
    fingerprint: str | None = None
    database: str | None = None
    error: ErrorSummary | None = None

    def __post_init__(self) -> None:
        """쿼리 이벤트의 ID, 시간, 기간, 선택 필드를 검증한다."""
        self.query_id = _require_text(self.query_id, "query_id")  # type: ignore[assignment]
        self.sequence = _validate_sequence(self.sequence)
        self.started_at = _normalize_datetime(self.started_at, "started_at")
        self.duration_ms = _validate_duration(self.duration_ms)
        self.statement = _require_text(
            self.statement,
            "statement",
            optional=True,
        )
        self.fingerprint = _require_text(
            self.fingerprint,
            "fingerprint",
            optional=True,
        )
        self.database = _require_text(
            self.database,
            "database",
            optional=True,
        )
        if self.error is not None and not isinstance(self.error, ErrorSummary):
            raise ValueError("error must be an ErrorSummary or None")


@dataclass
class RequestEvent:
    """HTTP 요청 하나와 연결된 쿼리 목록을 나타낸다."""

    request_id: str
    timestamp: datetime
    framework: str | Framework
    method: str
    route_template: str
    status_code: int
    duration_ms: float
    queries: list[QueryEvent] = field(default_factory=list)
    error: ErrorSummary | None = None
    query_count: int = field(init=False)
    query_time_ms: float = field(init=False)

    def __post_init__(self) -> None:
        """요청 필드를 검증하고 쿼리 집계값을 계산한다."""
        self.request_id = _require_text(  # type: ignore[assignment]
            self.request_id,
            "request_id",
        )
        self.timestamp = _normalize_datetime(self.timestamp, "timestamp")
        self.framework = self._normalize_framework(self.framework)
        self.method = _require_text(self.method, "method").upper()  # type: ignore[union-attr]
        self.route_template = _require_text(  # type: ignore[assignment]
            self.route_template,
            "route_template",
        )
        self.status_code = _validate_status_code(self.status_code)
        self.duration_ms = _validate_duration(self.duration_ms)
        self.queries = self._normalize_queries(self.queries)
        if self.error is not None and not isinstance(self.error, ErrorSummary):
            raise ValueError("error must be an ErrorSummary or None")
        self.query_count = len(self.queries)
        self.query_time_ms = round(
            sum(query.duration_ms for query in self.queries),
            6,
        )

    @staticmethod
    def _normalize_framework(value: str | Framework) -> str:
        """프레임워크 이름을 문자열로 통일한다."""
        if isinstance(value, Framework):
            return value.value
        normalized = _require_text(value, "framework")
        return normalized  # type: ignore[return-value]

    @staticmethod
    def _normalize_queries(value: Any) -> list[QueryEvent]:
        """쿼리 목록을 복사하고 순서와 타입을 검증한다."""
        if value is None:
            queries: list[QueryEvent] = []
        else:
            try:
                queries = list(value)
            except TypeError as error:
                raise ValueError("queries must be a list of QueryEvent") from error

        for expected_sequence, query in enumerate(queries, start=1):
            if not isinstance(query, QueryEvent):
                raise ValueError("queries must contain only QueryEvent values")
            if query.sequence != expected_sequence:
                raise ValueError("query sequence must start at 1 without gaps")
        return queries
