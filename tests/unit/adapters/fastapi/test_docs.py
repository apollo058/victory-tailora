"""FastAPI Swagger UI docs 어댑터의 URL·직렬화 계약을 검증한다."""

from fastapi import FastAPI

from tailora.adapters.fastapi.docs import (
    SUPPORTED_SWAGGER_UI_VERSION,
    get_docs_excluded_paths,
    render_tailora_swagger_ui_html,
)


def test_render_docs_html_uses_root_path_for_all_tailora_urls():
    """proxy root path가 OpenAPI와 Tailora plugin 자산 URL에 반영되는지 확인한다."""
    content = render_tailora_swagger_ui_html(
        openapi_url="/openapi.json",
        inspector_prefix="/diagnostics",
        root_path="/gateway",
    )

    assert 'url: "/gateway/openapi.json"' in content
    assert 'inspectorUrl: "/gateway/diagnostics"' in content
    assert "/gateway/diagnostics/swagger-plugin.js" in content
    assert "/gateway/diagnostics/swagger-plugin.css" in content


def test_render_docs_html_escapes_script_values():
    """경로 설정에 script 종료 문자열이 있어도 HTML을 탈출하지 못하는지 확인한다."""
    content = render_tailora_swagger_ui_html(
        openapi_url="/openapi.json</script><script>alert(1)</script>",
        inspector_prefix="/diagnostics",
    )

    assert "</script><script>alert(1)</script>" not in content
    assert "\\u003c/script\\u003e" in content


def test_docs_exclusion_uses_the_configured_docs_and_openapi_paths():
    """문서 수집 제외 경로가 FastAPI의 custom URL 설정을 따르는지 확인한다."""
    app = FastAPI(docs_url="/developer/docs", openapi_url="/schema/openapi.json")

    excluded_paths = get_docs_excluded_paths(app)

    assert excluded_paths == ("/developer/docs", "/schema/openapi.json")


def test_rendered_docs_records_the_supported_swagger_ui_version():
    """생성된 docs가 지원 범위를 벗어난 Swagger UI를 요청하지 않는지 확인한다."""
    content = render_tailora_swagger_ui_html(
        openapi_url="/openapi.json",
        inspector_prefix="/__tailora",
    )

    assert f"swagger-ui-dist@{SUPPORTED_SWAGGER_UI_VERSION}" in content
