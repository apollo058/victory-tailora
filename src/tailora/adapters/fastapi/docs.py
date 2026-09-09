"""FastAPI Swagger UI에 Tailora Inspector 탭을 연결하는 어댑터를 제공한다."""

import html
import json

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from tailora.adapters.fastapi.security import is_inspector_access_allowed
from tailora.config import AccessCheck

SUPPORTED_SWAGGER_UI_VERSION = "5.17.14"
_DEFAULT_DOCS_ROUTE_NAME = "swagger_ui_html"
_TAILORA_DOCS_ROUTE_NAME = "tailora_swagger_ui_html"


def get_docs_excluded_paths(app: FastAPI) -> tuple[str, ...]:
    """Inspector를 활성화할 때 수집에서 제외할 문서 경로를 반환한다."""
    paths = (app.docs_url, app.openapi_url)
    return tuple(path for path in paths if path is not None)


def install_tailora_docs(
    app: FastAPI,
    inspector_prefix: str,
    access_check: AccessCheck | None = None,
) -> bool:
    """기본 Swagger UI docs route를 Tailora plugin이 포함된 route로 교체한다."""
    docs_url = app.docs_url
    if docs_url is None or app.openapi_url is None:
        return False

    if not _remove_default_docs_route(app, docs_url):
        return False

    endpoint = _create_docs_endpoint(app, inspector_prefix, access_check)
    app.add_api_route(
        docs_url,
        endpoint,
        include_in_schema=False,
        methods=["GET"],
        name=_TAILORA_DOCS_ROUTE_NAME,
    )
    return True


def _remove_default_docs_route(app: FastAPI, docs_url: str) -> bool:
    """FastAPI가 만든 기본 Swagger UI route 하나만 제거한다."""
    for route in app.router.routes:
        is_docs_route = getattr(route, "path", None) == docs_url
        is_default_route = getattr(route, "name", None) == _DEFAULT_DOCS_ROUTE_NAME
        if is_docs_route and is_default_route:
            app.router.routes.remove(route)
            return True
    return False


def _create_docs_endpoint(
    app: FastAPI,
    inspector_prefix: str,
    access_check: AccessCheck | None,
):
    """요청의 root path를 반영해 Swagger UI HTML을 반환하는 endpoint를 만든다."""

    async def tailora_swagger_ui(request: Request) -> HTMLResponse:
        """현재 요청의 proxy root path를 반영한 docs HTML을 반환한다."""
        root_path = str(request.scope.get("root_path", ""))
        include_inspector = await is_inspector_access_allowed(
            request,
            access_check,
        )
        content = render_tailora_swagger_ui_html(
            openapi_url=app.openapi_url or "/openapi.json",
            inspector_prefix=inspector_prefix,
            root_path=root_path,
            include_inspector=include_inspector,
        )
        return HTMLResponse(content=content)

    return tailora_swagger_ui


def render_tailora_swagger_ui_html(
    openapi_url: str,
    inspector_prefix: str,
    root_path: str = "",
    include_inspector: bool = True,
) -> str:
    """Tailora plugin을 등록한 Swagger UI HTML을 안전한 URL 설정과 함께 생성한다."""
    inspector_url = _join_root_path(root_path, inspector_prefix)
    plugin_url = f"{inspector_url}/swagger-plugin.js"
    plugin_css_url = f"{inspector_url}/swagger-plugin.css"
    swagger_base_url = (
        f"https://cdn.jsdelivr.net/npm/swagger-ui-dist@{SUPPORTED_SWAGGER_UI_VERSION}"
    )
    if not include_inspector:
        return _render_base_docs_html(
            openapi_url=_join_root_path(root_path, openapi_url),
            swagger_css_url=f"{swagger_base_url}/swagger-ui.css",
            swagger_js_url=f"{swagger_base_url}/swagger-ui-bundle.js",
        )
    return _render_docs_html(
        openapi_url=_join_root_path(root_path, openapi_url),
        inspector_url=inspector_url,
        plugin_url=plugin_url,
        plugin_css_url=plugin_css_url,
        swagger_css_url=f"{swagger_base_url}/swagger-ui.css",
        swagger_js_url=f"{swagger_base_url}/swagger-ui-bundle.js",
    )


def _render_base_docs_html(
    openapi_url: str,
    swagger_css_url: str,
    swagger_js_url: str,
) -> str:
    """Inspector plugin을 노출하지 않는 기본 Swagger UI HTML을 만든다."""
    safe_openapi_url = _safe_script_json(openapi_url)
    safe_css_url, safe_js_url = _escape_asset_urls(
        swagger_css_url,
        swagger_js_url,
    )
    return f"""<!doctype html>
<html lang=\"ko\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>API Docs</title>
  <link rel=\"stylesheet\" href=\"{safe_css_url}\">
</head>
<body>
  <div id=\"swagger-ui\"></div>
  <script src=\"{safe_js_url}\"></script>
  <script>
    window.ui = SwaggerUIBundle({{
      url: {safe_openapi_url},
      dom_id: \"#swagger-ui\",
      deepLinking: true,
      presets: [
        SwaggerUIBundle.presets.apis,
        SwaggerUIBundle.SwaggerUIStandalonePreset
      ],
      layout: \"BaseLayout\"
    }});
  </script>
</body>
</html>"""


def _join_root_path(root_path: str, path: str) -> str:
    """root path와 앱 내부 절대 경로를 하나의 URL 경로로 결합한다."""
    normalized_root = root_path.strip().strip("/")
    normalized_path = path.strip()
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    if not normalized_root:
        return normalized_path
    return f"/{normalized_root}{normalized_path}"


def _render_docs_html(
    openapi_url: str,
    inspector_url: str,
    plugin_url: str,
    plugin_css_url: str,
    swagger_css_url: str,
    swagger_js_url: str,
) -> str:
    """Swagger UI 초기화와 plugin fallback이 포함된 HTML 문서를 구성한다."""
    config_script = _render_config_script(inspector_url)
    safe_urls = _escape_asset_urls(
        plugin_url,
        plugin_css_url,
        swagger_css_url,
        swagger_js_url,
    )
    return _render_docs_document(
        config_script=config_script,
        safe_openapi_url=_safe_script_json(openapi_url),
        safe_plugin_url=safe_urls[0],
        safe_plugin_css_url=safe_urls[1],
        safe_swagger_css_url=safe_urls[2],
        safe_swagger_js_url=safe_urls[3],
    )


def _escape_asset_urls(*urls: str) -> tuple[str, ...]:
    """HTML 속성에 넣을 정적 자산 URL을 안전하게 이스케이프한다."""
    return tuple(html.escape(url, quote=True) for url in urls)


def _render_docs_document(
    config_script: str,
    safe_openapi_url: str,
    safe_plugin_url: str,
    safe_plugin_css_url: str,
    safe_swagger_css_url: str,
    safe_swagger_js_url: str,
) -> str:
    """이미 안전하게 준비한 값으로 Swagger UI HTML 문서를 조립한다."""
    return f"""<!doctype html>
<html lang=\"ko\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>API Docs</title>
  <link rel=\"stylesheet\" href=\"{safe_swagger_css_url}\">
  <link rel=\"stylesheet\" href=\"{safe_plugin_css_url}\">
</head>
<body>
  <div id=\"tailora-plugin-warning\" role=\"status\" hidden></div>
  <div id=\"swagger-ui\"></div>
  <script>{config_script}</script>
  <script src=\"{safe_swagger_js_url}\"></script>
  <script src=\"{safe_plugin_url}\"
    onerror=\"window.TailoraSwaggerPluginLoadFailed = true\"></script>
  <script>
    (function () {{
      var plugin = window.TailoraSwaggerPlugin;
      var warning = document.getElementById(\"tailora-plugin-warning\");
      if (!plugin && warning) {{
        warning.hidden = false;
        warning.textContent =
          \"Inspector를 불러오지 못했습니다. API Docs는 계속 사용할 수 있습니다.\";
      }}
      window.ui = SwaggerUIBundle({{
        url: {safe_openapi_url},
        dom_id: \"#swagger-ui\",
        deepLinking: true,
        presets: [
          SwaggerUIBundle.presets.apis,
          SwaggerUIBundle.SwaggerUIStandalonePreset
        ],
        plugins: plugin ? [plugin] : [],
        layout: plugin ? \"TailoraDocsLayout\" : \"BaseLayout\"
      }});
    }})();
  </script>
</body>
</html>"""


def _render_config_script(inspector_url: str) -> str:
    """Swagger plugin이 사용할 Inspector URL 설정 스크립트를 생성한다."""
    return "\n".join(
        (
            "window.TAILORA_SWAGGER_CONFIG = {",
            f"  inspectorUrl: {_safe_script_json(inspector_url)}",
            "};",
        )
    )


def _safe_script_json(value: str) -> str:
    """script 태그 안에 넣어도 안전한 JSON 문자열 값을 반환한다."""
    return (
        json.dumps(value)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
