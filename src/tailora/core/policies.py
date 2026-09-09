"""Redaction 및 신호 임계값 정책 설정을 제공한다."""

from dataclasses import dataclass, field
import math

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
_MIN_ROUTE_LENGTH: int = 16
_MIN_HEADER_VALUE_LENGTH: int = 16
_MIN_QUERY_KEY_LENGTH: int = 16
_MAX_STATEMENT_LENGTH: int = 65536
_MAX_ERROR_LENGTH: int = 8192
_MAX_ROUTE_LENGTH: int = 8192
_MAX_HEADER_VALUE_LENGTH: int = 65536
_MAX_QUERY_KEY_LENGTH: int = 1024
_MAX_COLLECTION_COUNT: int = 1000
_MAX_DURATION_THRESHOLD_MS: float = 86_400_000.0


def _normalize_keys(values: frozenset[str], field_name: str) -> frozenset[str]:
    """차단 목록의 이름을 검증하고 소문자로 통일한다."""
    normalized: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must contain non-empty strings")
        normalized.add(value.strip().lower())
    return frozenset(normalized)


def _normalize_count(
    value: int,
    field_name: str,
    maximum: int = _MAX_COLLECTION_COUNT,
) -> int:
    """개수 제한이 0 이상이며 안전한 상한 이하인지 확인한다."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    if value > maximum:
        raise ValueError(f"{field_name} must be at most {maximum}")
    return value


def _normalize_length(
    value: int,
    field_name: str,
    minimum: int,
    maximum: int,
) -> int:
    """문자열 길이 제한이 안전한 최소·최대 범위인지 확인한다."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(
            f"{field_name} must be between {minimum} and {maximum}",
        )
    return value


def _validate_optional_positive_finite_float(
    value: float | int | None,
    field_name: str,
    maximum: float = _MAX_DURATION_THRESHOLD_MS,
) -> float | None:
    """임계값이 None이거나 0보다 큰 유한한 실숫값인지 검증한다."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number or None")
    val_float = float(value)
    if math.isnan(val_float) or math.isinf(val_float):
        raise ValueError(f"{field_name} must be a finite number")
    if val_float <= 0.0:
        raise ValueError(f"{field_name} must be positive")
    if val_float > maximum:
        raise ValueError(f"{field_name} must be at most {maximum}")
    return val_float


def _validate_optional_positive_int(
    value: int | None,
    field_name: str,
    min_val: int = 1,
    maximum: int = _MAX_COLLECTION_COUNT,
) -> int | None:
    """임계값이 None이거나 최소값 이상의 정수인지 검증한다."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer or None")
    if value < min_val:
        raise ValueError(f"{field_name} must be at least {min_val}")
    if value > maximum:
        raise ValueError(f"{field_name} must be at most {maximum}")
    return value


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
    max_route_length: int = 1024
    max_header_value_length: int = 4096
    max_query_key_length: int = 256
    max_queries_per_request: int = 200

    def __post_init__(self) -> None:
        """기본 차단 목록을 보장하고 모든 제한값을 안전하게 검증한다."""
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be a boolean")
        custom_headers = _normalize_keys(
            self.blocked_headers, "blocked_headers"
        )
        custom_keys = _normalize_keys(
            self.blocked_query_keys, "blocked_query_keys"
        )
        object.__setattr__(
            self,
            "blocked_headers",
            DEFAULT_BLOCKED_HEADERS | custom_headers,
        )
        object.__setattr__(
            self,
            "blocked_query_keys",
            DEFAULT_BLOCKED_QUERY_KEYS | custom_keys,
        )
        if not isinstance(self.redact_query_key_names, bool):
            raise ValueError("redact_query_key_names must be a boolean")
        self._validate_counts()
        self._validate_lengths()

    def _validate_counts(self) -> None:
        """헤더·파라미터·쿼리 개수 제한을 안전한 범위로 검증한다."""
        fields = ("max_headers", "max_query_params", "max_queries_per_request")
        for field_name in fields:
            value = _normalize_count(getattr(self, field_name), field_name)
            object.__setattr__(self, field_name, value)

    def _validate_lengths(self) -> None:
        """저장 또는 응답할 문자열의 길이 제한을 검증한다."""
        fields = (
            ("max_statement_length", _MIN_STATEMENT_LENGTH, _MAX_STATEMENT_LENGTH),
            ("max_error_length", _MIN_ERROR_LENGTH, _MAX_ERROR_LENGTH),
            ("max_route_length", _MIN_ROUTE_LENGTH, _MAX_ROUTE_LENGTH),
            (
                "max_header_value_length",
                _MIN_HEADER_VALUE_LENGTH,
                _MAX_HEADER_VALUE_LENGTH,
            ),
            ("max_query_key_length", _MIN_QUERY_KEY_LENGTH, _MAX_QUERY_KEY_LENGTH),
        )
        for field_name, minimum, maximum in fields:
            value = _normalize_length(
                getattr(self, field_name),
                field_name,
                minimum,
                maximum,
            )
            object.__setattr__(self, field_name, value)


@dataclass(frozen=True)
class ThresholdPolicy:
    """느린 요청, 느린 쿼리, 중복 쿼리 판정을 위한 임계값 설정을 담는다."""

    slow_request_ms: float | None = 500.0
    slow_query_ms: float | None = 100.0
    duplicate_query_threshold: int | None = 2
    query_heavy_count: int | None = 10
    query_heavy_time_ms: float | None = 200.0

    def __post_init__(self) -> None:
        """설정값이 유효한 양수이거나 None(비활성화)인지 검증한다."""
        object.__setattr__(
            self,
            "slow_request_ms",
            _validate_optional_positive_finite_float(
                self.slow_request_ms, "slow_request_ms"
            ),
        )
        object.__setattr__(
            self,
            "slow_query_ms",
            _validate_optional_positive_finite_float(
                self.slow_query_ms, "slow_query_ms"
            ),
        )
        object.__setattr__(
            self,
            "duplicate_query_threshold",
            _validate_optional_positive_int(
                self.duplicate_query_threshold,
                "duplicate_query_threshold",
                min_val=2,
            ),
        )
        object.__setattr__(
            self,
            "query_heavy_count",
            _validate_optional_positive_int(
                self.query_heavy_count,
                "query_heavy_count",
                min_val=1,
            ),
        )
        object.__setattr__(
            self,
            "query_heavy_time_ms",
            _validate_optional_positive_finite_float(
                self.query_heavy_time_ms,
                "query_heavy_time_ms",
            ),
        )
