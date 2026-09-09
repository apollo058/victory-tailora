"""Inspector 전체 설정 모델의 기본값과 보안 경계를 검증한다."""

import subprocess
import sys

import pytest

from tailora.config import InspectorConfig
from tailora.core.policies import RedactionPolicy, ThresholdPolicy


def test_config_import_does_not_load_optional_dependencies() -> None:
    """통합 설정을 가져와도 FastAPI와 SQLAlchemy를 강제로 불러오지 않는다."""
    script = """
import sys
import tailora.config

assert "fastapi" not in sys.modules
assert "sqlalchemy" not in sys.modules
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_default_config_is_disabled_and_bounded():
    """기본 설정이 Inspector를 끄고 안전한 저장·응답 한도를 제공하는지 확인한다."""
    config = InspectorConfig()

    assert config.enabled is False
    assert config.environment == "development"
    assert config.path_prefix == "/__tailora"
    assert config.store_capacity == 100
    assert config.api_default_limit == 20
    assert config.api_max_limit == 100
    assert config.redaction_policy.enabled is True


def test_config_normalizes_environment_and_path_prefix():
    """환경 이름과 Inspector 경로를 일관된 형식으로 정리하는지 확인한다."""
    config = InspectorConfig(
        environment=" Staging ",
        path_prefix="/diagnostics/",
    )

    assert config.environment == "staging"
    assert config.path_prefix == "/diagnostics"


@pytest.mark.parametrize(
    "path_prefix",
    ["diagnostics", "/", "/diagnostics?token=secret", "/a//b", "/a/../b"],
)
def test_config_rejects_unsafe_path_prefix(path_prefix):
    """상대 경로가 아니거나 충돌을 일으키기 쉬운 경로를 거부하는지 확인한다."""
    with pytest.raises(ValueError, match="path_prefix"):
        InspectorConfig(path_prefix=path_prefix)


@pytest.mark.parametrize("store_capacity", [0, -1, 10_001, True])
def test_config_rejects_invalid_store_capacity(store_capacity):
    """저장 용량이 양의 정수이며 안전한 상한 이하인지 확인한다."""
    with pytest.raises(ValueError, match="store_capacity"):
        InspectorConfig(store_capacity=store_capacity)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"api_default_limit": 0},
        {"api_max_limit": 0},
        {"api_max_limit": 1_001},
        {"api_default_limit": 101, "api_max_limit": 100},
    ],
)
def test_config_rejects_invalid_api_limits(kwargs):
    """API 기본 결과 수와 최대 결과 수의 안전한 범위를 검증한다."""
    with pytest.raises(ValueError, match="api_"):
        InspectorConfig(**kwargs)


def test_config_requires_second_confirmation_in_production():
    """production에서는 활성화와 별도 확인을 모두 요구하는지 확인한다."""
    with pytest.raises(ValueError, match="allow_in_production"):
        InspectorConfig(enabled=True, environment="production")

    config = InspectorConfig(
        enabled=True,
        environment="production",
        allow_in_production=True,
    )

    assert config.enabled is True
    assert config.is_production is True


def test_config_accepts_disabled_production_configuration():
    """production이라도 비활성 설정은 추가 확인 없이 생성되는지 확인한다."""
    config = InspectorConfig(environment="prod")

    assert config.enabled is False
    assert config.is_production is True


def test_production_region_name_is_treated_as_production():
    """production 접두사가 포함된 환경 이름도 production으로 보호한다."""
    with pytest.raises(ValueError, match="allow_in_production"):
        InspectorConfig(enabled=True, environment="production-seoul")


def test_config_rejects_disabled_redaction_policy():
    """Inspector 전체 흐름에서 Redaction을 끌 수 없는지 확인한다."""
    with pytest.raises(ValueError, match="redaction_policy"):
        InspectorConfig(redaction_policy=RedactionPolicy(enabled=False))


def test_config_accepts_custom_policies_and_access_check():
    """유효한 Redaction·임계값 정책과 접근 hook을 보관하는지 확인한다."""
    thresholds = ThresholdPolicy(slow_request_ms=250.0)

    def allow_request(request):
        """테스트 요청을 허용한다."""
        return request is not None

    config = InspectorConfig(
        threshold_policy=thresholds,
        access_check=allow_request,
    )

    assert config.threshold_policy is thresholds
    assert config.access_check is allow_request
