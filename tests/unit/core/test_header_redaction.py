"""헤더 redaction 동작을 확인한다."""

import pytest

from tailora.core.policies import RedactionPolicy
from tailora.core.privacy import REDACTED, redact_headers


def test_authorization_header_is_redacted():
    """Authorization 헤더 값이 [REDACTED]로 바뀌는지 확인한다."""
    result = redact_headers({"Authorization": "Bearer abc123"})
    assert result["Authorization"] == REDACTED


def test_cookie_header_is_redacted():
    """Cookie 헤더 값이 [REDACTED]로 바뀌는지 확인한다."""
    result = redact_headers({"Cookie": "session=xyz"})
    assert result["Cookie"] == REDACTED


def test_set_cookie_header_is_redacted():
    """Set-Cookie 헤더 값이 [REDACTED]로 바뀌는지 확인한다."""
    result = redact_headers({"Set-Cookie": "token=abc; Path=/"})
    assert result["Set-Cookie"] == REDACTED


def test_proxy_authorization_header_is_redacted():
    """Proxy-Authorization 헤더 값이 [REDACTED]로 바뀌는지 확인한다."""
    result = redact_headers({"Proxy-Authorization": "Basic dXNlcjpwYXNz"})
    assert result["Proxy-Authorization"] == REDACTED


def test_non_sensitive_header_passes_through():
    """민감하지 않은 헤더는 값이 그대로 유지되는지 확인한다."""
    result = redact_headers({"Content-Type": "application/json"})
    assert result["Content-Type"] == "application/json"


@pytest.mark.parametrize(
    "header_name",
    ["authorization", "COOKIE", "Authorization", "AUTHORIZATION"],
)
def test_header_matching_is_case_insensitive(header_name):
    """헤더 이름의 대소문자와 관계없이 redaction이 적용되는지 확인한다."""
    result = redact_headers({header_name: "sensitive-value"})
    assert result[header_name] == REDACTED


def test_custom_blocked_header_is_redacted():
    """사용자 지정 차단 헤더도 redaction이 적용되는지 확인한다."""
    policy = RedactionPolicy(blocked_headers=frozenset({"x-api-key"}))
    result = redact_headers({"X-Api-Key": "secret123"}, policy=policy)
    assert result["X-Api-Key"] == REDACTED


def test_custom_blocked_header_does_not_remove_defaults():
    """사용자 지정 헤더 추가 시 기본 차단 헤더가 유지되는지 확인한다."""
    policy = RedactionPolicy(blocked_headers=frozenset({"x-api-key"}))
    result = redact_headers(
        {"Authorization": "Bearer abc", "X-Api-Key": "secret"},
        policy=policy,
    )
    assert result["Authorization"] == REDACTED
    assert result["X-Api-Key"] == REDACTED


def test_original_headers_dict_is_not_modified():
    """원본 헤더 사전이 변경되지 않는지 확인한다."""
    original = {"Authorization": "Bearer abc", "Content-Type": "application/json"}
    original_copy = dict(original)
    redact_headers(original)
    assert original == original_copy


def test_empty_headers_returns_empty_dict():
    """헤더가 없으면 빈 사전을 반환하는지 확인한다."""
    result = redact_headers({})
    assert result == {}


def test_header_count_is_limited_by_policy():
    """헤더 개수가 정책의 최대값을 넘지 않는지 확인한다."""
    policy = RedactionPolicy(max_headers=1)

    result = redact_headers(
        {"Content-Type": "application/json", "X-Request-ID": "req-1"},
        policy=policy,
    )

    assert len(result) == 1


def test_non_sensitive_header_value_is_limited_by_policy():
    """차단 대상이 아닌 헤더 값도 설정한 최대 길이를 넘지 않는다."""
    policy = RedactionPolicy(max_header_value_length=64)

    result = redact_headers({"X-Debug-Info": "a" * 200}, policy=policy)

    assert len(result["X-Debug-Info"]) <= 64
    assert "[truncated]" in result["X-Debug-Info"]
