"""이벤트 모델의 입력값 검증을 확인한다."""

from datetime import datetime, timezone
import math

import pytest

from tailora.core.events import QueryEvent, RequestEvent


EVENT_TIME = datetime(2026, 8, 13, 10, 20, 30, tzinfo=timezone.utc)


def make_query(**overrides) -> QueryEvent:
    """검증 테스트용 기본 쿼리 이벤트를 만든다."""
    values = {
        "query_id": "q-1",
        "sequence": 1,
        "started_at": EVENT_TIME,
        "duration_ms": 1.0,
    }
    values.update(overrides)
    return QueryEvent(**values)


def make_request(**overrides) -> RequestEvent:
    """검증 테스트용 기본 요청 이벤트를 만든다."""
    values = {
        "request_id": "req-1",
        "timestamp": EVENT_TIME,
        "framework": "fastapi",
        "method": "GET",
        "route_template": "/health",
        "status_code": 200,
        "duration_ms": 1.0,
    }
    values.update(overrides)
    return RequestEvent(**values)


@pytest.mark.parametrize("duration_ms", [-1.0, math.nan, math.inf])
def test_query_duration_must_be_non_negative_and_finite(duration_ms):
    """쿼리 시간은 음수가 아니고 유한한 값이어야 하는지 확인한다."""
    with pytest.raises(ValueError, match="duration_ms"):
        make_query(duration_ms=duration_ms)


@pytest.mark.parametrize("duration_ms", [-1.0, math.nan, math.inf])
def test_request_duration_must_be_non_negative_and_finite(duration_ms):
    """요청 시간은 음수가 아니고 유한한 값이어야 하는지 확인한다."""
    with pytest.raises(ValueError, match="duration_ms"):
        make_request(duration_ms=duration_ms)


@pytest.mark.parametrize("status_code", [99, 600, True])
def test_status_code_must_be_an_http_status(status_code):
    """상태 코드는 HTTP 상태 코드 범위의 정수여야 하는지 확인한다."""
    with pytest.raises(ValueError, match="status_code"):
        make_request(status_code=status_code)


@pytest.mark.parametrize(
    "field",
    ["request_id", "framework", "method", "route_template"],
)
def test_required_text_fields_cannot_be_empty(field):
    """필수 문자열 필드가 비어 있으면 거부하는지 확인한다."""
    with pytest.raises(ValueError, match=field):
        make_request(**{field: ""})


def test_query_id_cannot_be_empty():
    """쿼리 ID가 비어 있으면 거부하는지 확인한다."""
    with pytest.raises(ValueError, match="query_id"):
        make_query(query_id="")


def test_text_fields_trim_surrounding_whitespace():
    """문자열 필드의 앞뒤 공백을 제거하는지 확인한다."""
    event = make_request(
        request_id=" req-1 ",
        framework=" fastapi ",
        method=" get ",
        route_template=" /health ",
    )

    assert event.request_id == "req-1"
    assert event.framework == "fastapi"
    assert event.method == "GET"
    assert event.route_template == "/health"


def test_timestamp_must_include_timezone():
    """시각에 timezone 정보가 없으면 거부하는지 확인한다."""
    naive_time = datetime(2026, 8, 13, 10, 20, 30)

    with pytest.raises(ValueError, match="timezone"):
        make_request(timestamp=naive_time)


def test_request_normalizes_timestamp_to_utc():
    """다른 timezone의 시각을 UTC로 정규화하는지 확인한다."""
    from datetime import timedelta

    offset_time = datetime(
        2026,
        8,
        13,
        19,
        20,
        30,
        tzinfo=timezone(timedelta(hours=9)),
    )

    event = make_request(timestamp=offset_time)

    assert event.timestamp == EVENT_TIME
    assert event.timestamp.tzinfo == timezone.utc


def test_query_sequences_must_start_at_one_without_gaps():
    """요청 안의 쿼리 순서가 1부터 연속이어야 하는지 확인한다."""
    queries = [make_query(sequence=1), make_query(sequence=3)]

    with pytest.raises(ValueError, match="sequence"):
        make_request(queries=queries)
