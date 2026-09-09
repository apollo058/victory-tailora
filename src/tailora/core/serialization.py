"""이벤트 모델을 JSON으로 바꾸고 다시 읽는 기능을 제공한다."""

from datetime import datetime
import json
from typing import Any, Mapping

from tailora.core.events import ErrorSummary, QueryEvent, RequestEvent


def _format_datetime(value: datetime) -> str:
    """UTC 시각을 ISO 8601 문자열로 바꾼다."""
    return value.isoformat().replace("+00:00", "Z")


def _parse_datetime(value: Any, field_name: str) -> datetime:
    """ISO 8601 문자열을 datetime으로 바꾼다."""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO 8601 string")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} must be an ISO 8601 string") from error


def _required(data: Mapping[str, Any], field_name: str) -> Any:
    """직렬화 데이터에서 필수 필드를 가져온다."""
    if field_name not in data:
        raise ValueError(f"missing required field: {field_name}")
    return data[field_name]


def _error_to_dict(error: ErrorSummary | None) -> dict[str, str | None] | None:
    """오류 요약을 JSON용 사전으로 바꾼다."""
    if error is None:
        return None
    return {
        "type": error.type,
        "message": error.message,
        "stack_hint": error.stack_hint,
    }


def _error_from_value(value: Any) -> ErrorSummary | None:
    """JSON의 오류 사전을 오류 요약 객체로 바꾼다."""
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("error must be an object or null")
    return ErrorSummary(
        type=_required(value, "type"),
        message=value.get("message"),
        stack_hint=value.get("stack_hint"),
    )


def query_event_to_dict(event: QueryEvent) -> dict[str, Any]:
    """쿼리 이벤트를 JSON용 사전으로 바꾼다."""
    if not isinstance(event, QueryEvent):
        raise TypeError("event must be a QueryEvent")
    return {
        "query_id": event.query_id,
        "sequence": event.sequence,
        "started_at": _format_datetime(event.started_at),
        "duration_ms": event.duration_ms,
        "statement": event.statement,
        "fingerprint": event.fingerprint,
        "database": event.database,
        "error": _error_to_dict(event.error),
    }


def query_event_from_dict(data: Mapping[str, Any]) -> QueryEvent:
    """JSON용 사전에서 쿼리 이벤트를 만든다."""
    if not isinstance(data, Mapping):
        raise ValueError("query event must be an object")
    return QueryEvent(
        query_id=_required(data, "query_id"),
        sequence=_required(data, "sequence"),
        started_at=_parse_datetime(_required(data, "started_at"), "started_at"),
        duration_ms=_required(data, "duration_ms"),
        statement=data.get("statement"),
        fingerprint=data.get("fingerprint"),
        database=data.get("database"),
        error=_error_from_value(data.get("error")),
    )


def request_event_to_dict(event: RequestEvent) -> dict[str, Any]:
    """요청 이벤트를 JSON용 사전으로 바꾼다."""
    if not isinstance(event, RequestEvent):
        raise TypeError("event must be a RequestEvent")
    return {
        "request_id": event.request_id,
        "timestamp": _format_datetime(event.timestamp),
        "framework": event.framework,
        "method": event.method,
        "route_template": event.route_template,
        "status_code": event.status_code,
        "duration_ms": event.duration_ms,
        "query_count": event.query_count,
        "query_time_ms": event.query_time_ms,
        "total_query_count": event.total_query_count,
        "total_query_time_ms": event.total_query_time_ms,
        "is_queries_truncated": event.is_queries_truncated,
        "queries": [query_event_to_dict(query) for query in event.queries],
        "error": _error_to_dict(event.error),
    }


def request_event_from_dict(data: Mapping[str, Any]) -> RequestEvent:
    """JSON용 사전에서 요청 이벤트를 만든다."""
    if not isinstance(data, Mapping):
        raise ValueError("request event must be an object")
    query_data = data.get("queries", [])
    if query_data is None:
        query_data = []
    elif not isinstance(query_data, list):
        raise ValueError("queries must be a list")
    return RequestEvent(
        request_id=_required(data, "request_id"),
        timestamp=_parse_datetime(_required(data, "timestamp"), "timestamp"),
        framework=_required(data, "framework"),
        method=_required(data, "method"),
        route_template=_required(data, "route_template"),
        status_code=_required(data, "status_code"),
        duration_ms=_required(data, "duration_ms"),
        queries=[query_event_from_dict(item) for item in query_data],
        error=_error_from_value(data.get("error")),
        total_query_count=data.get("total_query_count"),
        total_query_time_ms=data.get("total_query_time_ms"),
    )


def request_event_to_json(event: RequestEvent) -> str:
    """요청 이벤트를 JSON 문자열로 바꾼다."""
    return json.dumps(request_event_to_dict(event), ensure_ascii=False)


def request_event_from_json(value: str) -> RequestEvent:
    """JSON 문자열에서 요청 이벤트를 만든다."""
    try:
        data = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("value must be valid JSON") from error
    return request_event_from_dict(data)
