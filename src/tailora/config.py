"""Inspector 전체에서 공통으로 사용할 안전한 설정을 제공한다."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
import re
from typing import Any

from tailora.core.policies import RedactionPolicy, ThresholdPolicy
from tailora.core.store import DEFAULT_CAPACITY, MAX_CAPACITY

AccessCheck = Callable[[Any], bool | Awaitable[bool]]

MAX_API_LIMIT = 1_000
_PRODUCTION_ENVIRONMENTS = frozenset({"prod", "production"})
_ENVIRONMENT_PATTERN = re.compile(r"^[a-z0-9_-]{1,32}$")
_PATH_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9._~-]+$")


def _validate_boolean(value: object, field_name: str) -> bool:
    """bool 설정이 정확한 자료형인지 확인한다."""
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _validate_positive_integer(
    value: object,
    field_name: str,
    maximum: int,
) -> int:
    """설정값이 안전한 상한 이하의 양의 정수인지 확인한다."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")
    if value > maximum:
        raise ValueError(f"{field_name} must be at most {maximum}")
    return value


def _normalize_environment(value: object) -> str:
    """환경 이름을 로그와 보안 판단에 안전한 형식으로 정리한다."""
    if not isinstance(value, str):
        raise ValueError("environment must be a string")
    normalized = value.strip().lower()
    if not _ENVIRONMENT_PATTERN.fullmatch(normalized):
        raise ValueError(
            "environment must contain only letters, numbers, '_' or '-'",
        )
    return normalized


def normalize_path_prefix(value: object, field_name: str = "path_prefix") -> str:
    """Inspector 경로를 충돌과 우회가 없는 절대 경로로 정리한다."""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized.startswith("/") or normalized == "/":
        raise ValueError(f"{field_name} must be an absolute non-root path")
    if len(normalized) > 255 or "?" in normalized or "#" in normalized:
        raise ValueError(f"{field_name} contains unsupported characters")
    if "\\" in normalized or "//" in normalized:
        raise ValueError(f"{field_name} contains an unsafe path segment")
    normalized = normalized.rstrip("/")
    segments = normalized.removeprefix("/").split("/")
    if any(
        segment in {"", ".", ".."}
        or _PATH_SEGMENT_PATTERN.fullmatch(segment) is None
        for segment in segments
    ):
        raise ValueError(f"{field_name} contains an unsafe path segment")
    return normalized


def _normalize_excluded_paths(values: object) -> tuple[str, ...]:
    """사용자 지정 제외 경로를 검증하고 중복을 제거한다."""
    if not isinstance(values, tuple):
        raise ValueError("excluded_paths must be a tuple of paths")
    normalized = [
        normalize_path_prefix(value, "excluded_paths") for value in values
    ]
    return tuple(dict.fromkeys(normalized))


@dataclass(frozen=True)
class InspectorConfig:
    """Inspector의 활성화, 보안 정책, 자원 한도를 하나로 관리한다."""

    enabled: bool = False
    environment: str = "development"
    allow_in_production: bool = False
    path_prefix: str = "/__tailora"
    store_capacity: int = DEFAULT_CAPACITY
    api_default_limit: int = 20
    api_max_limit: int = 100
    redaction_policy: RedactionPolicy = field(default_factory=RedactionPolicy)
    threshold_policy: ThresholdPolicy = field(default_factory=ThresholdPolicy)
    access_check: AccessCheck | None = None
    excluded_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """모든 설정을 등록 전에 검증하고 안전한 형식으로 정리한다."""
        object.__setattr__(self, "enabled", _validate_boolean(self.enabled, "enabled"))
        object.__setattr__(
            self,
            "allow_in_production",
            _validate_boolean(self.allow_in_production, "allow_in_production"),
        )
        object.__setattr__(
            self,
            "environment",
            _normalize_environment(self.environment),
        )
        object.__setattr__(
            self,
            "path_prefix",
            normalize_path_prefix(self.path_prefix),
        )
        self._validate_limits()
        self._validate_policies()
        if self.access_check is not None and not callable(self.access_check):
            raise ValueError("access_check must be callable or None")
        object.__setattr__(
            self,
            "excluded_paths",
            _normalize_excluded_paths(self.excluded_paths),
        )
        if self.enabled and self.is_production and not self.allow_in_production:
            raise ValueError(
                "allow_in_production must be True to enable Inspector "
                "in production",
            )

    @property
    def is_production(self) -> bool:
        """현재 환경이 production으로 분류되는지 반환한다."""
        return self.environment in _PRODUCTION_ENVIRONMENTS or (
            self.environment.startswith("prod-")
            or self.environment.startswith("production-")
        )

    def _validate_limits(self) -> None:
        """저장소와 API 결과 수 한도의 범위와 관계를 검증한다."""
        object.__setattr__(
            self,
            "store_capacity",
            _validate_positive_integer(
                self.store_capacity,
                "store_capacity",
                MAX_CAPACITY,
            ),
        )
        default_limit = _validate_positive_integer(
            self.api_default_limit,
            "api_default_limit",
            MAX_API_LIMIT,
        )
        maximum_limit = _validate_positive_integer(
            self.api_max_limit,
            "api_max_limit",
            MAX_API_LIMIT,
        )
        if default_limit > maximum_limit:
            raise ValueError("api_default_limit must not exceed api_max_limit")
        object.__setattr__(self, "api_default_limit", default_limit)
        object.__setattr__(self, "api_max_limit", maximum_limit)

    def _validate_policies(self) -> None:
        """Redaction과 신호 임계값 정책의 자료형과 보안 조건을 검증한다."""
        if not isinstance(self.redaction_policy, RedactionPolicy):
            raise ValueError("redaction_policy must be a RedactionPolicy")
        if not self.redaction_policy.enabled:
            raise ValueError("redaction_policy must remain enabled")
        if not isinstance(self.threshold_policy, ThresholdPolicy):
            raise ValueError("threshold_policy must be a ThresholdPolicy")
