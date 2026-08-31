"""Inspector API 응답을 화면 ViewModel로 변환하는 로직을 검증하는 단위 테스트."""

from tailora.ui.view_model import (
    transform_request_detail,
    transform_request_summary,
)


def test_transform_request_summary():
    """목록 항목 API 응답이 화면 표시용 필드로 올바르게 변환되는지 확인한다."""
    raw_item = {
        "request_id": "req-123",
        "method": "get",
        "route_template": "/items",
        "status_code": 200,
        "duration_ms": 550.2,
        "query_count": 3,
        "query_time_ms": 40.5,
        "signals": {
            "slow_request": True,
            "has_duplicate_query": True,
            "has_slow_query": False,
            "query_heavy": False,
        },
    }

    vm = transform_request_summary(raw_item)
    assert vm["request_id"] == "req-123"
    assert vm["method"] == "GET"
    assert vm["route_template"] == "/items"
    assert vm["status_code"] == 200
    assert vm["duration_ms"] == 550.2
    assert vm["is_slow"] is True
    assert vm["has_dup"] is True
    assert vm["has_slow_query"] is False
    assert vm["is_heavy"] is False


def test_transform_request_detail():
    """상세 API 응답이 화면 상세 및 쿼리 표 뷰모델로 올바르게 변환되는지 확인한다."""
    raw_detail = {
        "request_id": "req-456",
        "timestamp": "2026-08-31T12:00:00Z",
        "framework": "fastapi",
        "method": "post",
        "route_template": "/users",
        "status_code": 201,
        "duration_ms": 120.0,
        "query_count": 2,
        "query_time_ms": 65.0,
        "error": None,
        "signals": {
            "slow_request": False,
            "slow_queries": [2],
            "duplicate_queries": [
                {
                    "fingerprint": "select 1",
                    "count": 2,
                    "sequences": [1, 2],
                }
            ],
            "query_heavy": True,
            "query_heavy_reasons": ["time"],
            "applied_thresholds": {
                "slow_request_ms": 500.0,
                "slow_query_ms": 50.0,
            },
        },
        "queries": [
            {
                "sequence": 1,
                "duration_ms": 10.0,
                "database": "sqlite",
                "statement": "SELECT 1",
                "fingerprint": "select 1",
            },
            {
                "sequence": 2,
                "duration_ms": 55.0,
                "database": "sqlite",
                "statement": "SELECT 1",
                "fingerprint": "select 1",
            },
        ],
    }

    vm = transform_request_detail(raw_detail)
    assert vm["request_id"] == "req-456"
    assert vm["timestamp"] == "2026-08-31T12:00:00Z"
    assert vm["framework"] == "fastapi"
    assert vm["method"] == "POST"
    assert vm["is_slow_request"] is False
    assert vm["query_heavy"] is True
    assert vm["query_heavy_reasons"] == ["time"]
    assert vm["slow_request_threshold_ms"] == 500.0
    assert vm["slow_query_threshold_ms"] == 50.0

    queries = vm["queries"]
    assert len(queries) == 2
    assert queries[0]["sequence"] == 1
    assert queries[0]["is_slow"] is False
    assert queries[0]["fingerprint"] == "select 1"
    assert queries[1]["sequence"] == 2
    assert queries[1]["is_slow"] is True
