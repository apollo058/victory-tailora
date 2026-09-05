"""FastAPI Swagger UI와 Tailora Inspector 탭의 통합 계약을 검증한다."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tailora.adapters.fastapi import enable_inspector


def create_docs_app(
    docs_url: str | None = "/docs",
    openapi_url: str | None = "/openapi.json",
) -> tuple[FastAPI, TestClient]:
    """Swagger UI 설정을 가진 테스트용 FastAPI 앱과 클라이언트를 생성한다."""
    app = FastAPI(docs_url=docs_url, openapi_url=openapi_url)
    client = TestClient(app)
    return app, client


def test_enabled_inspector_adds_plugin_to_existing_docs_page():
    """Inspector 활성화 시 기존 docs URL에 plugin이 포함되는지 확인한다."""
    app, client = create_docs_app()

    enable_inspector(app)

    response = client.get("/docs")

    assert response.status_code == 200
    assert "TailoraSwaggerPlugin" in response.text
    assert "/__tailora/swagger-plugin.js" in response.text
    assert "/__tailora/swagger-plugin.css" in response.text
    assert "swagger-ui-dist@5.17.14" in response.text


def test_plugin_assets_are_served_from_the_inspector_prefix():
    """Swagger plugin JavaScript와 CSS가 Inspector prefix에서 제공되는지 확인한다."""
    app, client = create_docs_app()

    enable_inspector(app)

    plugin_response = client.get("/__tailora/swagger-plugin.js")
    stylesheet_response = client.get("/__tailora/swagger-plugin.css")

    assert plugin_response.status_code == 200
    assert "application/javascript" in plugin_response.headers["content-type"]
    assert "TailoraSwaggerPlugin" in plugin_response.text
    assert stylesheet_response.status_code == 200
    assert "text/css" in stylesheet_response.headers["content-type"]


def test_custom_inspector_prefix_is_passed_to_docs_plugin():
    """사용자 지정 Inspector prefix가 docs plugin 설정에 반영되는지 확인한다."""
    app, client = create_docs_app()

    enable_inspector(app, prefix="/diagnostics")

    response = client.get("/docs")

    assert response.status_code == 200
    assert "/diagnostics/swagger-plugin.js" in response.text
    assert "/diagnostics/swagger-plugin.css" in response.text
    assert 'inspectorUrl: "/diagnostics"' in response.text


def test_custom_docs_url_and_root_path_are_reflected_in_asset_urls():
    """custom docs URL과 proxy root path에서도 plugin 자산 URL이 맞는지 확인한다."""
    app = FastAPI(docs_url="/developer/docs", root_path="/gateway")
    client = TestClient(app)

    enable_inspector(app, prefix="/diagnostics")

    response = client.get("/developer/docs")

    assert response.status_code == 200
    assert "/gateway/openapi.json" in response.text
    assert "/gateway/diagnostics/swagger-plugin.js" in response.text
    assert "/gateway/diagnostics/swagger-plugin.css" in response.text


def test_docs_related_requests_are_not_collected():
    """docs, OpenAPI와 plugin 자산 요청이 이벤트 저장소를 오염시키지 않는지 확인한다."""
    app, client = create_docs_app()
    store = enable_inspector(app)

    client.get("/docs")
    client.get("/openapi.json")
    client.get("/__tailora/swagger-plugin.js")
    client.get("/__tailora/swagger-plugin.css")

    assert store.size() == 0


def test_disabled_inspector_keeps_default_docs_without_plugin():
    """Inspector가 비활성일 때 기존 Swagger UI에 plugin이 없는지 확인한다."""
    _, client = create_docs_app()

    response = client.get("/docs")

    assert response.status_code == 200
    assert "TailoraSwaggerPlugin" not in response.text
