"""Redaction 정책 설정을 제공한다."""

from dataclasses import dataclass, field

DEFAULT_BLOCKED_HEADERS: frozenset[str] = frozenset({
    "authorization",
    "cookie",
    "set-cookie",
    "proxy-authorization",
})

DEFAULT_BLOCKED_QUERY_KEYS: frozenset[str] = frozenset({
    "token",
    "key",
    "password",
    "secret",
    "code",
    "api_key",
    "access_token",
    "refresh_token",
})

_MIN_STATEMENT_LENGTH: int = 64
_MIN_ERROR_LENGTH: int = 32
_MAX_STATEMENT_LENGTH: int = 65536
_MAX_ERROR_LENGTH: int = 8192


def _normalize_keys(values: frozenset[str], field_name: str) -> frozenset[str]:
    """차단 목록의 이름을 검증하고 소문자로 통일한다."""
    normalized: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must contain non-empty strings")
        normalized.add(value.strip().lower())
    return frozenset(normalized)


def _normalize_count(value: int, field_name: str) -> int:
    """개수 제한이 0 이상인 정수인지 확인한다."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _normalize_length(
    value: int,
    field_name: str,
    minimum: int,
    maximum: int,
) -> int:
    """문자열 길이 제한을 안전한 범위로 보정한다."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    return min(max(value, minimum), maximum)


@dataclass(frozen=True)
class RedactionPolicy:
    """이벤트 저장 전 적용할 개인정보 보호 규칙을 담는다."""

    enabled: bool = True
    blocked_headers: frozenset[str] = field(
        default_factory=lambda: DEFAULT_BLOCKED_HEADERS,
    )
    blocked_query_keys: frozenset[str] = field(
        default_factory=lambda: DEFAULT_BLOCKED_QUERY_KEYS,
    )
    redact_query_key_names: bool = False
    max_headers: int = 100
    max_query_params: int = 100
    max_statement_length: int = 4096
    max_error_length: int = 512
    max_queries_per_request: int = 200

    def __post_init__(self) -> None:
        """기본 차단 목록을 보장하고 설정값을 안전한 범위로 보정한다."""
        custom_headers = _normalize_keys(self.blocked_headers, "blocked_headers")
        merged_headers = DEFAULT_BLOCKED_HEADERS | custom_headers
        object.__setattr__(self, "blocked_headers", merged_headers)

        custom_keys = _normalize_keys(self.blocked_query_keys, "blocked_query_keys")
        merged_keys = DEFAULT_BLOCKED_QUERY_KEYS | custom_keys
        object.__setattr__(self, "blocked_query_keys", merged_keys)

        if not isinstance(self.redact_query_key_names, bool):
            raise ValueError("redact_query_key_names must be a boolean")

        object.__setattr__(
            self,
            "max_headers",
            _normalize_count(self.max_headers, "max_headers"),
        )
        object.__setattr__(
            self,
            "max_query_params",
            _normalize_count(self.max_query_params, "max_query_params"),
        )
        object.__setattr__(
            self,
            "max_queries_per_request",
            _normalize_count(
                self.max_queries_per_request,
                "max_queries_per_request",
            ),
        )
        object.__setattr__(
            self,
            "max_statement_length",
            _normalize_length(
                self.max_statement_length,
                "max_statement_length",
                _MIN_STATEMENT_LENGTH,
                _MAX_STATEMENT_LENGTH,
            ),
        )
        object.__setattr__(
            self,
            "max_error_length",
            _normalize_length(
                self.max_error_length,
                "max_error_length",
                _MIN_ERROR_LENGTH,
                _MAX_ERROR_LENGTH,
            ),
        )
