"""이벤트의 민감한 값을 제거하는 기능을 제공한다."""

import dataclasses
import re
from typing import Mapping

from tailora.core.events import ErrorSummary, QueryEvent, RequestEvent
from tailora.core.limits import truncate_list, truncate_str
from tailora.core.policies import RedactionPolicy

REDACTED: str = "[REDACTED]"

_NUMBER_LITERAL: re.Pattern[str] = re.compile(r"\b\d+(?:\.\d+)?\b")
_ERROR_TYPE_PATTERN: re.Pattern[str] = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
_DATABASE_NAME_PATTERN: re.Pattern[str] = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_DIALECT_NAME_PATTERN: re.Pattern[str] = re.compile(r"[A-Za-z0-9_-]{1,32}")
_DOLLAR_QUOTE_OPEN: re.Pattern[str] = re.compile(
    r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$",
)


def _make_unique_bounded_key(
    key: str,
    index: int,
    existing: Mapping[str, str],
    max_length: int,
) -> str:
    """중복 키를 정해진 길이 안에서 고유한 이름으로 바꾼다."""
    if key not in existing:
        return key
    attempt = index
    while True:
        suffix = f"_{attempt}"
        candidate = f"{key[: max_length - len(suffix)]}{suffix}"
        if candidate not in existing:
            return candidate
        attempt += 1


def redact_headers(
    headers: Mapping[str, str],
    policy: RedactionPolicy | None = None,
) -> dict[str, str]:
    """헤더에서 민감한 값을 제거하고 새 사전으로 반환한다.

    원본 사전은 변경하지 않으며, 정책의 최대 헤더 수를 넘는 항목은 버린다.
    헤더 이름은 대소문자를 구분하지 않고 차단 목록과 비교한다.
    """
    if policy is None:
        policy = RedactionPolicy()
    result: dict[str, str] = {}
    for index, (name, value) in enumerate(headers.items()):
        if index >= policy.max_headers:
            break
        if name.lower() in policy.blocked_headers:
            result[name] = REDACTED
        else:
            result[name] = truncate_str(
                value,
                policy.max_header_value_length,
            ) or ""
    return result


def redact_query_params(
    params: Mapping[str, str | list[str]],
    policy: RedactionPolicy | None = None,
) -> dict[str, str]:
    """쿼리 파라미터의 값을 가리고 새 사전으로 반환한다.

    기본 정책은 모든 값을 가리며, 설정에 따라 민감한 키 이름도 가린다.
    원본 사전은 변경하지 않고 최대 항목 수를 넘는 값은 버린다.
    """
    if policy is None:
        policy = RedactionPolicy()
    result: dict[str, str] = {}
    for index, (key, _) in enumerate(params.items()):
        if index >= policy.max_query_params:
            break
        safe_key = key
        if policy.redact_query_key_names and key.strip().lower() in (
            policy.blocked_query_keys
        ):
            safe_key = REDACTED
        safe_key = truncate_str(safe_key, policy.max_query_key_length) or REDACTED
        safe_key = _make_unique_bounded_key(
            safe_key,
            index,
            result,
            policy.max_query_key_length,
        )
        result[safe_key] = REDACTED
    return result


def redact_sql_statement(
    statement: str | None,
    policy: RedactionPolicy | None = None,
    *,
    dialect: str | None = None,
) -> str | None:
    """SQL의 리터럴·주석을 제거하고 길이를 제한한다.

    처리 중 오류가 발생하면 None을 반환해 원문이 저장되지 않도록 한다.
    """
    if policy is None:
        policy = RedactionPolicy()
    if statement is None:
        return None
    try:
        safe = _redact_sql_fragments(statement, dialect)
        result = truncate_str(safe, policy.max_statement_length)
        return result or None
    except Exception:
        return None


def make_sql_fingerprint(
    statement: str | None,
    *,
    dialect: str | None = None,
) -> str | None:
    """SQL 원문에서 값을 정규화한 fingerprint 문자열을 만든다.

    리터럴과 주석을 제거하고, 공백을 정규화하며 소문자로 변환한다.
    """
    if statement is None:
        return None
    try:
        fingerprint = _redact_sql_fragments(statement, dialect)
        fingerprint = re.sub(r"\s+", " ", fingerprint).strip().lower()
        return fingerprint or None
    except Exception:
        return None


def redact_error_summary(
    error: ErrorSummary | None,
) -> ErrorSummary | None:
    """오류 원문과 경로는 버리고 안전한 오류 타입만 남긴다.

    오류 문구는 사용자 입력이나 연결 정보가 섞일 수 있어 정규식 마스킹에
    기대지 않는다.
    """
    if error is None:
        return None
    try:
        safe_type = error.type
        if _ERROR_TYPE_PATTERN.fullmatch(safe_type) is None:
            safe_type = "Error"
        return ErrorSummary(type=safe_type)
    except Exception:
        return ErrorSummary(type="Error")


def _redact_sql_fragments(statement: str, dialect: str | None = None) -> str:
    """SQL 문자열·주석·숫자 리터럴을 순서대로 제거한다."""
    fragments: list[str] = []
    index = 0
    while index < len(statement):
        if statement.startswith("--", index):
            index = _redact_line_comment(statement, index, fragments)
            continue
        if statement.startswith("#", index) and _uses_hash_comments(dialect):
            index = _redact_line_comment(statement, index, fragments, "#")
            continue
        if statement.startswith("/*", index):
            index = _redact_block_comment(statement, index, fragments)
            continue
        if statement[index] in "'\"`":
            fragments.append("?")
            index = _skip_quoted_value(statement, index, statement[index])
            continue
        dollar_match = _DOLLAR_QUOTE_OPEN.match(statement, index)
        if dollar_match is not None:
            fragments.append("?")
            index = _skip_dollar_quoted_value(
                statement,
                index,
                dollar_match.group(),
            )
            continue
        fragments.append(statement[index])
        index += 1
    return _NUMBER_LITERAL.sub("?", "".join(fragments))


def _redact_line_comment(
    statement: str,
    index: int,
    fragments: list[str],
    marker: str = "--",
) -> int:
    """SQL 한 줄 주석의 내용을 제거하고 다음 줄 위치를 반환한다."""
    fragments.append(f"{marker} {REDACTED}")
    line_end = statement.find("\n", index + len(marker))
    if line_end == -1:
        return len(statement)
    fragments.append("\n")
    return line_end + 1


def _uses_hash_comments(dialect: str | None) -> bool:
    """해시 주석 문법을 쓰는 DB이거나 방언이 알려지지 않았는지 확인한다."""
    if dialect is None:
        return True
    return dialect.strip().lower() in {"mysql", "mariadb"}


def _redact_block_comment(
    statement: str,
    index: int,
    fragments: list[str],
) -> int:
    """SQL 여러 줄 주석의 내용을 제거하고 다음 위치를 반환한다."""
    fragments.append(f"/* {REDACTED} */")
    comment_end = statement.find("*/", index + 2)
    if comment_end == -1:
        return len(statement)
    return comment_end + 2


def _skip_quoted_value(statement: str, index: int, quote: str) -> int:
    """SQL 따옴표 값의 끝을 찾고 닫히지 않은 값도 끝까지 건너뛴다."""
    index += 1
    while index < len(statement):
        if statement[index] == "\\" and index + 1 < len(statement):
            index += 2
            continue
        if statement[index] == quote:
            if index + 1 < len(statement) and statement[index + 1] == quote:
                index += 2
                continue
            return index + 1
        index += 1
    return len(statement)


def _skip_dollar_quoted_value(statement: str, index: int, marker: str) -> int:
    """PostgreSQL dollar-quoted 값의 끝을 찾는다."""
    value_start = index + len(marker)
    value_end = statement.find(marker, value_start)
    if value_end == -1:
        return len(statement)
    return value_end + len(marker)


def _redact_query_event(
    query: QueryEvent,
    policy: RedactionPolicy,
) -> QueryEvent:
    """쿼리 이벤트의 민감한 필드를 제거하고 새 이벤트를 반환한다."""
    safe_fingerprint = _safe_query_fingerprint(
        query.statement,
        policy,
        query.dialect,
    )
    safe_database = query.database
    if safe_database is not None and (
        _DATABASE_NAME_PATTERN.fullmatch(safe_database) is None
    ):
        safe_database = "database"
    safe_dialect = query.dialect
    if safe_dialect is not None and (
        _DIALECT_NAME_PATTERN.fullmatch(safe_dialect) is None
    ):
        safe_dialect = None
    return dataclasses.replace(
        query,
        statement=redact_sql_statement(
            query.statement,
            policy,
            dialect=query.dialect,
        ),
        fingerprint=safe_fingerprint,
        database=safe_database,
        error=redact_error_summary(query.error),
        dialect=safe_dialect,
    )


def _safe_query_fingerprint(
    statement: str | None,
    policy: RedactionPolicy,
    dialect: str | None,
) -> str | None:
    """안전한 SQL statement에서만 fingerprint를 다시 만든다."""
    if statement is None:
        return None
    return truncate_str(
        make_sql_fingerprint(statement, dialect=dialect),
        policy.max_statement_length,
    )


def redact_event(
    event: RequestEvent,
    policy: RedactionPolicy | None = None,
) -> RequestEvent:
    """이벤트를 저장소에 넣기 전에 민감 정보를 제거한 새 이벤트를 반환한다.

    원본 이벤트 객체는 변경하지 않는다.
    policy.enabled가 False이면 원본 이벤트를 그대로 반환한다.
    """
    if policy is None:
        policy = RedactionPolicy()
    if not policy.enabled:
        return event

    limited_queries, _ = truncate_list(
        event.queries,
        policy.max_queries_per_request,
    )
    redacted_queries = [_redact_query_event(q, policy) for q in limited_queries]

    return dataclasses.replace(
        event,
        route_template=(
            truncate_str(event.route_template, policy.max_route_length) or "/"
        ),
        queries=redacted_queries,
        error=redact_error_summary(event.error),
    )
