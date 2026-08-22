"""임계값 설정 모델(ThresholdPolicy)의 유효성을 검증한다."""

import pytest

from tailora.core.policies import ThresholdPolicy


def test_default_threshold_policy_values():
    """ThresholdPolicy의 기본 설정값이 기획 명세와 일치하는지 확인한다."""
    policy = ThresholdPolicy()

    assert policy.slow_request_ms == 500.0
    assert policy.slow_query_ms == 100.0
    assert policy.duplicate_query_threshold == 2
    assert policy.query_heavy_count == 10
    assert policy.query_heavy_time_ms == 200.0


def test_custom_threshold_policy_values():
    """사용자 지정 유효한 임계값이 올바르게 설정되는지 확인한다."""
    policy = ThresholdPolicy(
        slow_request_ms=200.0,
        slow_query_ms=50.0,
        duplicate_query_threshold=3,
        query_heavy_count=5,
        query_heavy_time_ms=150.0,
    )

    assert policy.slow_request_ms == 200.0
    assert policy.slow_query_ms == 50.0
    assert policy.duplicate_query_threshold == 3
    assert policy.query_heavy_count == 5
    assert policy.query_heavy_time_ms == 150.0


def test_threshold_policy_supports_none_for_disabling():
    """신호별 임계값을 None으로 설정해 비활성화할 수 있는지 확인한다."""
    policy = ThresholdPolicy(
        slow_request_ms=None,
        slow_query_ms=None,
        duplicate_query_threshold=None,
        query_heavy_count=None,
        query_heavy_time_ms=None,
    )

    assert policy.slow_request_ms is None
    assert policy.slow_query_ms is None
    assert policy.duplicate_query_threshold is None
    assert policy.query_heavy_count is None
    assert policy.query_heavy_time_ms is None


@pytest.mark.parametrize(
    "kwargs, match_msg",
    [
        ({"slow_request_ms": 0}, "slow_request_ms must be positive"),
        ({"slow_request_ms": -10.0}, "slow_request_ms must be positive"),
        ({"slow_request_ms": float("nan")}, "slow_request_ms must be a finite"),
        ({"slow_request_ms": float("inf")}, "slow_request_ms must be a finite"),
        ({"slow_query_ms": 0}, "slow_query_ms must be positive"),
        ({"slow_query_ms": -1.0}, "slow_query_ms must be positive"),
        (
            {"duplicate_query_threshold": 1},
            "duplicate_query_threshold must be at least 2",
        ),
        (
            {"duplicate_query_threshold": 0},
            "duplicate_query_threshold must be at least 2",
        ),
        ({"query_heavy_count": 0}, "query_heavy_count must be at least 1"),
        ({"query_heavy_count": -5}, "query_heavy_count must be at least 1"),
        ({"query_heavy_time_ms": 0}, "query_heavy_time_ms must be positive"),
        (
            {"query_heavy_time_ms": -100.0},
            "query_heavy_time_ms must be positive",
        ),
    ],
)
def test_invalid_threshold_policy_raises_value_error(kwargs, match_msg):
    """유효하지 않은 임계값 입력 시 ValueError 발생을 확인한다."""
    with pytest.raises(ValueError, match=match_msg):
        ThresholdPolicy(**kwargs)
