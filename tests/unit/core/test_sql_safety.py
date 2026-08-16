"""SQL statement 처리와 fingerprint 생성을 확인한다."""


from tailora.core.limits import truncate_str
from tailora.core.policies import RedactionPolicy
from tailora.core.privacy import make_sql_fingerprint, redact_sql_statement


def test_string_literal_is_replaced():
    """SQL의 문자열 리터럴이 ?로 교체되는지 확인한다."""
    result = redact_sql_statement("SELECT * FROM users WHERE name = 'Alice'")
    assert result is not None
    assert "Alice" not in result
    assert "?" in result


def test_number_literal_is_replaced():
    """SQL의 숫자 리터럴이 ?로 교체되는지 확인한다."""
    result = redact_sql_statement("SELECT * FROM users WHERE id = 42")
    assert result is not None
    assert "42" not in result
    assert "?" in result


def test_none_input_returns_none():
    """입력이 None이면 None을 반환하는지 확인한다."""
    assert redact_sql_statement(None) is None


def test_statement_is_truncated_at_max_length():
    """statement가 최대 길이를 초과하면 잘려나가는지 확인한다."""
    long_sql = "SELECT " + "a" * 5000
    policy = RedactionPolicy(max_statement_length=100)
    result = redact_sql_statement(long_sql, policy)
    assert result is not None
    assert len(result) <= 100
    assert "truncated" in result


def test_statement_within_limit_is_not_truncated():
    """최대 길이 이내의 statement는 잘리지 않는지 확인한다."""
    sql = "SELECT * FROM users"
    result = redact_sql_statement(sql)
    assert result is not None
    assert "truncated" not in result


def test_both_string_and_number_literals_are_replaced():
    """문자열·숫자 리터럴이 모두 교체되는지 확인한다."""
    sql = "SELECT * FROM orders WHERE user_id = 1 AND status = 'paid'"
    result = redact_sql_statement(sql)
    assert result is not None
    assert "paid" not in result
    assert "1" not in result


def test_sql_comments_and_dollar_quoted_literals_are_redacted():
    """SQL 주석과 dollar-quoted 문자열의 값도 제거하는지 확인한다."""
    sql = "SELECT $$Alice$$ -- token=secret\nFROM users /* email=alice@example.com */"

    result = redact_sql_statement(sql)

    assert result is not None
    assert "Alice" not in result
    assert "secret" not in result
    assert "alice@example.com" not in result


def test_unterminated_sql_string_is_redacted_to_the_end():
    """닫히지 않은 SQL 문자열도 끝까지 안전하게 처리하는지 확인한다."""
    result = redact_sql_statement("SELECT 'secret value")

    assert result is not None
    assert "secret value" not in result


def test_sql_fingerprint_normalizes_literals():
    """fingerprint 생성 시 리터럴이 ?로 교체되는지 확인한다."""
    fp = make_sql_fingerprint("SELECT * FROM users WHERE id = 42 AND name = 'Alice'")
    assert fp is not None
    assert "42" not in fp
    assert "Alice" not in fp


def test_sql_fingerprint_is_lowercase():
    """fingerprint가 소문자로 반환되는지 확인한다."""
    fp = make_sql_fingerprint("SELECT * FROM Users WHERE ID = 1")
    assert fp is not None
    assert fp == fp.lower()


def test_sql_fingerprint_normalizes_whitespace():
    """fingerprint에서 연속 공백이 단일 공백으로 정규화되는지 확인한다."""
    fp1 = make_sql_fingerprint("SELECT *  FROM  users")
    fp2 = make_sql_fingerprint("SELECT * FROM users")
    assert fp1 is not None
    assert fp1 == fp2


def test_sql_fingerprint_with_none_returns_none():
    """fingerprint 생성에 None을 넘기면 None을 반환하는지 확인한다."""
    assert make_sql_fingerprint(None) is None


def test_default_policy_is_used_when_none_given():
    """policy를 넘기지 않아도 기본 정책으로 동작하는지 확인한다."""
    result = redact_sql_statement("SELECT 1")
    assert result is not None


def test_truncate_str_never_exceeds_requested_length():
    """문자열 제한 결과가 요청한 최대 길이를 넘지 않는지 확인한다."""
    result = truncate_str("abcdef", 5)

    assert result is not None
    assert len(result) <= 5
