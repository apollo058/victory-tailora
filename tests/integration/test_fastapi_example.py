"""FastAPI 예제의 기본 동작을 확인한다."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from fastapi.testclient import TestClient


def load_example_app():
    """저장소의 FastAPI 예제 앱을 파일 경로로 불러온다."""
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
    return module.app


def test_health_endpoint_returns_ok():
    """health endpoint가 정상 상태를 반환하는지 확인한다."""
    client = TestClient(load_example_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
