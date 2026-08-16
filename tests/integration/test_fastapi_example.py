"""FastAPI 예제의 기본 동작을 확인한다."""

from fastapi.testclient import TestClient

from examples.fastapi.app import app


def test_health_endpoint_returns_ok():
    """health endpoint가 정상 상태를 반환하는지 확인한다."""
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
