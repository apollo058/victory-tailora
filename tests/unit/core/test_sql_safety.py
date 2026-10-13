"""SQL statement 처리와 fingerprint 생성을 확인한다."""

import random
import sqlite3

import pytest

from tailora.core.limits import truncate_str
from tailora.core.policies import RedactionPolicy
from tailora.core.privacy import make_sql_fingerprint, redact_sql_statement
from tailora.core.privacy import MAX_SQL_INPUT_LENGTH


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


@pytest.mark.parametrize(
    ("dialect", "statement", "secret"),
    [
        ("sqlite", "SELECT 'prefix\\' || 'tailora-secret'", "tailora-secret"),
        ("oracle", "SELECT q'!it's tailora-secret!' FROM dual", "tailora-secret"),
        ("oracle", "SELECT nq'[it's tailora-secret]' FROM dual", "tailora-secret"),
        (
            "postgresql",
            "SELECT 1 /* outer /* inner */ tailora-secret */",
            "tailora-secret",
        ),
        ("mssql", "SELECT 1 /* outer /* inner */ tailora-secret */", "tailora-secret"),
        ("postgresql", "SELECT $태그$tailora-secret$태그$", "tailora-secret"),
        ("postgresql", "SELECT $🐈$tailora-secret$🐈$", "tailora-secret"),
        ("postgresql", "SELECT E'prefix\\'tailora-secret'", "tailora-secret"),
        ("mssql", "SELECT [col'umn], 'tailora-secret'", "tailora-secret"),
        ("sqlite", "SELECT 987654321e5", "987654321"),
        ("sqlite", "SELECT 0xABCDEF", "ABCDEF"),
        ("postgresql", "SELECT 987_654_321, .987654321", "987"),
    ],
)
def test_dialect_specific_literals_and_comments_do_not_leak(dialect, statement, secret):
    """동일한 비밀값이 SQL과 fingerprint 어느 쪽에도 남지 않는다."""
    for value in (
        redact_sql_statement(statement, dialect=dialect),
        make_sql_fingerprint(statement, dialect=dialect),
    ):
        assert value is not None
        assert secret.lower() not in value.lower()


@pytest.mark.parametrize("dialect", [None, "mysql", "mariadb", "postgresql"])
def test_ambiguous_backslash_modes_drop_sql_and_fingerprint(dialect):
    """접속 SQL mode에 따라 다르게 해석되는 문자열은 저장하지 않는다."""
    statement = "SELECT 'prefix\\' || 'tailora-secret'"
    assert redact_sql_statement(statement, dialect=dialect) is None
    assert make_sql_fingerprint(statement, dialect=dialect) is None


def test_unknown_dialect_does_not_guess_its_literal_syntax():
    """지원하지 않는 SQL 방언의 쿼리 원문은 버린다."""
    assert redact_sql_statement("SELECT custom_literal", dialect="custom") is None
    assert make_sql_fingerprint("SELECT custom_literal", dialect="custom") is None


def test_oversized_sql_is_dropped_before_scanning(monkeypatch):
    """출력 잘림과 별도로 원문 처리에도 상한을 적용한다."""
    import tailora.core.privacy as privacy

    def fail_if_scanned(*args, **kwargs):
        raise AssertionError("oversized input was scanned")

    monkeypatch.setattr(privacy, "_skip_oracle_quoted_value", fail_if_scanned)
    statement = "S" * (MAX_SQL_INPUT_LENGTH + 1)
    assert redact_sql_statement(statement) is None
    assert make_sql_fingerprint(statement) is None


def test_generated_valid_sqlite_literals_never_leak():
    """SQLite가 실제 실행한 여러 인용·백슬래시 조합에서 값 노출을 검사한다."""
    generator = random.Random(731)
    alphabet = "abc'\\\n\r\t![]$/*-한글"
    with sqlite3.connect(":memory:") as connection:
        for _ in range(250):
            value = "tailora-secret-" + "".join(generator.choices(alphabet, k=35))
            literal = "'" + value.replace("'", "''") + "'"
            statement = "SELECT " + literal + " || 'second-secret'"
            assert (
                connection.execute(statement).fetchone()[0] == value + "second-secret"
            )
            assert redact_sql_statement(statement, dialect="sqlite") == "SELECT ? || ?"
            assert make_sql_fingerprint(statement, dialect="sqlite") == "select ? || ?"
