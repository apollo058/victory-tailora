"""쿼리 파라미터 redaction 동작을 확인한다."""

from tailora.core.policies import RedactionPolicy
from tailora.core.privacy import REDACTED, redact_query_params


def test_all_query_param_values_are_redacted():
    """쿼리 파라미터의 모든 값이 [REDACTED]로 바뀌는지 확인한다."""
    result = redact_query_params({"user_id": "42", "page": "1"})
    assert result["user_id"] == REDACTED
    assert result["page"] == REDACTED


def test_empty_params_returns_empty_dict():
    """파라미터가 없으면 빈 사전을 반환하는지 확인한다."""
    result = redact_query_params({})
    assert result == {}


def test_sensitive_key_names_are_also_redacted():
    """민감한 키 이름의 파라미터 값도 redaction되는지 확인한다."""
    result = redact_query_params({"password": "secret", "token": "abc"})
    assert result["password"] == REDACTED
    assert result["token"] == REDACTED


def test_param_keys_are_preserved():
    """파라미터 이름(키)은 그대로 유지되는지 확인한다."""
    result = redact_query_params({"user_id": "42", "search": "hello"})
    assert set(result.keys()) == {"user_id", "search"}


def test_original_params_dict_is_not_modified():
    """원본 파라미터 사전이 변경되지 않는지 확인한다."""
    original = {"token": "abc123", "page": "1"}
    original_copy = dict(original)
    redact_query_params(original)
    assert original == original_copy


def test_multiple_params_all_values_are_redacted():
    """여러 파라미터가 모두 [REDACTED] 값으로 바뀌는지 확인한다."""
    params = {"a": "1", "b": "2", "c": "3"}
    result = redact_query_params(params)
    assert all(v == REDACTED for v in result.values())
    assert set(result.keys()) == {"a", "b", "c"}


def test_custom_policy_does_not_change_redaction_behavior():
    """커스텀 정책을 넘겨도 기본 redaction 동작이 유지되는지 확인한다."""
    policy = RedactionPolicy(blocked_query_keys=frozenset({"x-extra"}))
    result = redact_query_params({"name": "Alice"}, policy=policy)
    assert result["name"] == REDACTED


def test_query_param_count_is_limited_by_policy():
    """쿼리 파라미터 개수가 정책의 최대값을 넘지 않는지 확인한다."""
    policy = RedactionPolicy(max_query_params=1)

    result = redact_query_params(
        {"first": "1", "second": "2"},
        policy=policy,
    )

    assert len(result) == 1


def test_blocked_query_key_names_can_be_hidden():
    """정책을 켜면 민감한 쿼리 키 이름도 숨기는지 확인한다."""
    policy = RedactionPolicy(
        blocked_query_keys=frozenset({"password"}),
        redact_query_key_names=True,
    )

    result = redact_query_params({"password": "secret", "page": "1"}, policy)

    assert "password" not in result
    assert result["page"] == REDACTED
