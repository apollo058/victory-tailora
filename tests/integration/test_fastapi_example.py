"""FastAPI 예제의 기본 동작을 확인한다."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from fastapi.testclient import TestClient
import pytest


def load_example_module():
    """저장소의 FastAPI 예제 모듈을 파일 경로로 불러온다."""
    app_path = (
        Path(__file__).resolve().parents[2]
        / "examples"
        / "fastapi"
        / "app.py"
    )
    spec = spec_from_file_location("tailora_fastapi_example", app_path)

    if spec is None or spec.loader is None:
        raise RuntimeError("FastAPI 예제 앱을 불러올 수 없다.")

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_health_endpoint_returns_ok_and_records_event():
    """헬스체크 엔드포인트가 정상 응답하고 이벤트를 기록하는지 확인한다."""
    module = load_example_module()
    client = TestClient(module.app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert module.store.size() == 1

    event = module.store.list()[0]
    assert event.route_template == "/health"
    assert event.status_code == 200
    assert event.framework == "fastapi"
    assert event.query_count == 0


def test_user_endpoint_executes_query_and_records_event():
    """사용자 조회 시 SQL 쿼리가 실행되고 이벤트에 쿼리가 연결되는지 확인한다."""
    module = load_example_module()
    client = TestClient(module.app)

    response = client.get("/users/1")

    assert response.status_code == 200
    assert response.json() == {"id": "1", "name": "Alice"}
    assert module.store.size() == 1

    event = module.store.list()[0]
    assert event.route_template == "/users/{user_id}"
    assert event.query_count == 1
    assert len(event.queries) == 1
    assert event.queries[0].database == "sqlite"
    assert event.queries[0].statement == "SELECT name FROM users WHERE id = ?"


def test_repeat_user_endpoint_records_duplicate_queries():
    """반복 조회 endpoint가 동일 fingerprint를 두 번 기록하는지 확인한다."""
    module = load_example_module()
    client = TestClient(module.app)

    response = client.get("/users/repeat/1")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {"id": "1", "name": "Alice"},
            {"id": "1", "name": "Alice"},
        ],
    }
    event = module.store.list()[0]
    assert event.query_count == 2
    assert event.queries[0].fingerprint == event.queries[1].fingerprint


def test_slow_request_exposes_slow_request_signal():
    """느린 요청 endpoint가 설정된 threshold를 넘는 신호를 남기는지 확인한다."""
    module = load_example_module()
    client = TestClient(module.app)

    response = client.get("/slow")

    assert response.status_code == 200
    event = module.store.list()[0]
    assert event.duration_ms >= 25
    signal_response = client.get("/__tailora/requests")
    assert signal_response.status_code == 200
    assert signal_response.json()["items"][0]["signals"]["slow_request"] is True


def test_slow_query_exposes_slow_query_signal_without_storing_parameters():
    """느린 SQL 함수가 측정되고 실행 인자는 저장되지 않는지 확인한다."""
    module = load_example_module()
    client = TestClient(module.app)

    response = client.get("/slow-query")

    assert response.status_code == 200
    event = module.store.list()[0]
    assert event.query_count == 1
    assert event.queries[0].duration_ms >= 15
    assert "0.03" not in repr(event)
    detail = client.get(f"/__tailora/requests/{event.request_id}")
    assert detail.status_code == 200
    assert detail.json()["signals"]["slow_queries"] == [1]


def test_secret_query_redacts_sql_literal_before_storage():
    """SQL literal을 실행해도 응답과 Inspector 이벤트에 원문이 남지 않는지 확인한다."""
    module = load_example_module()
    client = TestClient(module.app)

    response = client.get("/secret-query")

    assert response.status_code == 200
    assert "sql-demo-secret" not in response.text
    event = module.store.list()[0]
    assert event.query_count == 1
    assert event.queries[0].statement == "SELECT ? AS value"
    assert "sql-demo-secret" not in repr(event)


def test_http_error_preserves_response_and_redacts_secret_detail():
    """HTTP 오류 응답을 유지하면서 저장 이벤트의 비밀값을 가리는지 확인한다."""
    module = load_example_module()
    client = TestClient(module.app)

    response = client.get("/secret-error?token=demo-secret")

    assert response.status_code == 400
    assert response.json()["detail"]["message"] == "Invalid token provided"
    event = module.store.list()[0]
    assert event.error is not None
    assert "demo-secret" not in repr(event)
    assert "demo-secret" not in response.text


def test_database_error_preserves_500_response_and_failed_query():
    """DB 오류가 500 응답으로 전달되고 실패 쿼리가 안전하게 기록되는지 확인한다."""
    module = load_example_module()
    client = TestClient(module.app, raise_server_exceptions=False)

    response = client.get("/db-error")

    assert response.status_code == 500
    event = module.store.list()[0]
    assert event.status_code == 500
    assert event.query_count == 1
    assert event.queries[0].error is not None
    assert "no such column" in (event.queries[0].error.message or "").lower()


@pytest.mark.parametrize("path", ["/docs", "/openapi.json", "/__tailora/health"])
def test_example_internal_routes_are_not_captured(path: str):
    """예제의 문서와 Inspector 내부 요청이 진단 이벤트를 오염시키지 않는지 확인한다."""
    module = load_example_module()
    client = TestClient(module.app)

    response = client.get(path)

    assert response.status_code == 200
    assert module.store.size() == 0
