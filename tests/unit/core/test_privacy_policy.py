"""RedactionPolicy 설정과 redact_event 통합 흐름을 확인한다."""

from datetime import datetime, timezone

import pytest

from tailora.core.events import ErrorSummary, QueryEvent, RequestEvent
from tailora.core.policies import (
    RedactionPolicy,
)
from tailora.core.privacy import redact_event
from tailora.core.privacy import redact_error_summary


EVENT_TIME = datetime(2026, 8, 13, 10, 20, 30, tzinfo=timezone.utc)


def make_query(sequence: int, statement: str | None = None) -> QueryEvent:
    """테스트용 쿼리 이벤트를 만든다."""
    return QueryEvent(
        query_id=f"q-{sequence}",
        sequence=sequence,
        started_at=EVENT_TIME,
        duration_ms=1.0,
        statement=statement,
    )


def make_event(
    queries: list[QueryEvent] | None = None,
    error: ErrorSummary | None = None,
) -> RequestEvent:
    """테스트용 요청 이벤트를 만든다."""
    return RequestEvent(
        request_id="req-1",
        timestamp=EVENT_TIME,
        framework="fastapi",
        method="GET",
        route_template="/health",
        status_code=200,
        duration_ms=10.0,
        queries=queries or [],
        error=error,
    )


# --- RedactionPolicy 기본값 테스트 ---


def test_default_policy_is_enabled():
    """기본 정책에서 redaction이 활성화되어 있는지 확인한다."""
    policy = RedactionPolicy()
    assert policy.enabled is True


def test_default_policy_includes_authorization_header():
    """기본 정책에 Authorization 헤더가 포함되어 있는지 확인한다."""
    policy = RedactionPolicy()
    assert "authorization" in policy.blocked_headers


def test_default_policy_includes_cookie_header():
    """기본 정책에 Cookie 헤더가 포함되어 있는지 확인한다."""
    policy = RedactionPolicy()
    assert "cookie" in policy.blocked_headers


def test_default_policy_includes_set_cookie_header():
    """기본 정책에 Set-Cookie 헤더가 포함되어 있는지 확인한다."""
    policy = RedactionPolicy()
    assert "set-cookie" in policy.blocked_headers


def test_custom_blocked_headers_are_merged_with_defaults():
    """사용자 지정 헤더가 기본 차단 목록과 합쳐지는지 확인한다."""
    policy = RedactionPolicy(blocked_headers=frozenset({"x-custom-secret"}))
    assert "x-custom-secret" in policy.blocked_headers
    assert "authorization" in policy.blocked_headers


def test_custom_blocked_query_keys_are_merged_with_defaults():
    """사용자 지정 파라미터 키가 기본 차단 목록과 합쳐지는지 확인한다."""
    policy = RedactionPolicy(blocked_query_keys=frozenset({"my_secret_param"}))
    assert "my_secret_param" in policy.blocked_query_keys
    assert "token" in policy.blocked_query_keys


def test_max_statement_length_below_minimum_is_corrected():
    """최대 statement 길이가 최솟값 이하면 최솟값으로 보정되는지 확인한다."""
    policy = RedactionPolicy(max_statement_length=1)
    assert policy.max_statement_length >= 64


def test_max_error_length_below_minimum_is_corrected():
    """최대 오류 메시지 길이가 최솟값 이하면 최솟값으로 보정되는지 확인한다."""
    policy = RedactionPolicy(max_error_length=1)
    assert policy.max_error_length >= 32


@pytest.mark.parametrize(
    "field_name",
    ["max_headers", "max_query_params", "max_queries_per_request"],
)
def test_count_limits_reject_negative_values(field_name):
    """개수 제한에 음수가 들어오면 거부하는지 확인한다."""
    with pytest.raises(ValueError, match=field_name):
        RedactionPolicy(**{field_name: -1})


# --- redact_event 통합 테스트 ---


def test_redact_event_returns_new_object():
    """redact_event가 원본을 변경하지 않고 새 객체를 반환하는지 확인한다."""
    event = make_event()
    result = redact_event(event)
    assert result is not event


def test_redact_event_does_not_modify_original_query_statement():
    """redact_event 호출 후 원본 쿼리의 statement가 변경되지 않는지 확인한다."""
    query = make_query(1, statement="SELECT * FROM users WHERE name = 'Alice'")
    event = make_event(queries=[query])
    original_statement = query.statement

    redact_event(event)

    assert query.statement == original_statement


def test_redact_event_redacts_sql_literals_in_queries():
    """redact_event가 쿼리의 SQL 리터럴을 제거하는지 확인한다."""
    query = make_query(1, statement="SELECT * FROM users WHERE name = 'Alice'")
    event = make_event(queries=[query])

    result = redact_event(event)

    assert "Alice" not in (result.queries[0].statement or "")


def test_redact_event_sanitizes_existing_query_fingerprint():
    """redact_event가 이미 들어온 fingerprint도 안전하게 바꾸는지 확인한다."""
    query = make_query(1, statement=None)
    query.fingerprint = "select users where email = 'Alice@example.com'"
    event = make_event(queries=[query])

    result = redact_event(event)

    assert result.queries[0].fingerprint is None


def test_redact_event_redacts_dsn_in_error_message():
    """redact_event가 오류 메시지의 연결 문자열을 제거하는지 확인한다."""
    error = ErrorSummary(
        type="DatabaseError",
        message="connection failed: postgresql://user:pass@host/db",
    )
    event = make_event(error=error)

    result = redact_event(event)

    assert result.error is not None
    assert "pass" not in (result.error.message or "")


def test_redact_error_summary_removes_secret_assignments_and_windows_paths():
    """오류 메시지의 비밀값과 Windows 경로를 제거하는지 확인한다."""
    error = ErrorSummary(
        type="RuntimeError",
        message=(
            "token=secret password=hunter2 "
            r"C:\Users\victory\project\app.py:42"
        ),
    )

    result = redact_error_summary(error)

    assert result is not None
    assert "secret" not in (result.message or "")
    assert "hunter2" not in (result.message or "")
    assert r"C:\Users\victory\project" not in (result.message or "")


def test_redact_event_preserves_error_type():
    """redact_event 후에도 오류 타입 이름은 유지되는지 확인한다."""
    error = ErrorSummary(type="ValueError", message="something went wrong")
    event = make_event(error=error)

    result = redact_event(event)

    assert result.error is not None
    assert result.error.type == "ValueError"


def test_redact_event_with_disabled_policy_returns_same_object():
    """정책이 비활성화되면 원본 이벤트 객체를 그대로 반환하는지 확인한다."""
    policy = RedactionPolicy(enabled=False)
    query = make_query(1, statement="SELECT * WHERE name = 'Alice'")
    event = make_event(queries=[query])

    result = redact_event(event, policy=policy)

    assert result is event


def test_redact_event_limits_queries_to_max_count():
    """redact_event가 쿼리 수를 최대값으로 제한하는지 확인한다."""
    policy = RedactionPolicy(max_queries_per_request=2)
    queries = [make_query(i) for i in range(1, 5)]  # 4개 쿼리
    event = make_event(queries=queries)

    result = redact_event(event, policy=policy)

    assert len(result.queries) == 2


def test_redact_event_query_count_reflects_truncation():
    """쿼리가 잘린 경우 query_count도 줄어드는지 확인한다."""
    policy = RedactionPolicy(max_queries_per_request=2)
    queries = [make_query(i) for i in range(1, 5)]
    event = make_event(queries=queries)

    result = redact_event(event, policy=policy)

    assert result.query_count == 2


def test_redact_event_with_no_error_keeps_none():
    """오류가 없는 이벤트는 오류 필드가 None으로 유지되는지 확인한다."""
    event = make_event()
    result = redact_event(event)
    assert result.error is None


def test_redact_error_summary_removes_file_path():
    """오류 요약의 stack_hint에서 파일 경로가 제거되는지 확인한다."""
    error = ErrorSummary(
        type="RuntimeError",
        stack_hint="/home/user/app/handlers.py:42",
    )
    policy = RedactionPolicy()
    result = redact_error_summary(error, policy)

    assert result is not None
    assert "/home/user/app/handlers.py" not in (result.stack_hint or "")


def test_redact_error_summary_truncates_long_message():
    """오류 메시지가 최대 길이를 초과하면 잘리는지 확인한다."""
    long_message = "error " * 200
    error = ErrorSummary(type="RuntimeError", message=long_message)
    policy = RedactionPolicy(max_error_length=100)
    result = redact_error_summary(error, policy)

    assert result is not None
    assert len(result.message or "") <= 100


def test_redact_error_summary_with_none_returns_none():
    """오류가 None이면 None을 반환하는지 확인한다."""
    assert redact_error_summary(None) is None
