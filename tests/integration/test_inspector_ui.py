"""FastAPI 어댑터를 통한 Inspector UI 정적 자산 제공 및 이벤트 수집 제외 검증."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tailora.adapters.fastapi import enable_inspector


def test_ui_index_endpoint_serves_html():
    """GET /__tailora 및 /__tailora/ 요청 시 200 OK와 HTML을 반환하는지 확인한다."""
    app = FastAPI()
    enable_inspector(app, prefix="/__tailora", enabled=True)
    client = TestClient(app)

    # 슬래시 있는 경로와 없는 경로 모두 지원
    resp1 = client.get("/__tailora")
    assert resp1.status_code == 200
    assert "text/html; charset=utf-8" in resp1.headers["content-type"]
    assert '<meta name="tailora-base-path" content="/__tailora">' in resp1.text

    resp2 = client.get("/__tailora/")
    assert resp2.status_code == 200
    assert "text/html; charset=utf-8" in resp2.headers["content-type"]
    assert '<meta name="tailora-base-path" content="/__tailora">' in resp2.text


def test_ui_assets_endpoint_serves_css_and_js():
    """styles.css 및 app.js 요청 시 적절한 Content-Type으로 반환하는지 확인한다."""
    app = FastAPI()
    enable_inspector(app, prefix="/__tailora", enabled=True)
    client = TestClient(app)

    resp_css = client.get("/__tailora/styles.css")
    assert resp_css.status_code == 200
    assert "text/css; charset=utf-8" in resp_css.headers["content-type"]
    assert len(resp_css.text) > 0

    resp_js = client.get("/__tailora/app.js")
    assert resp_js.status_code == 200
    assert "application/javascript; charset=utf-8" in resp_js.headers["content-type"]
    assert len(resp_js.text) > 0


def test_ui_asset_not_found_returns_404():
    """존재하지 않는 자산 요청 시 404와 안전한 요약 메시지를 반환하는지 확인한다."""
    app = FastAPI()
    enable_inspector(app, prefix="/__tailora", enabled=True)
    client = TestClient(app)

    resp = client.get("/__tailora/non_existent.png")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "asset_not_found"
    assert data["error"]["message"] == "Requested static asset was not found."


def test_ui_requests_are_excluded_from_collection():
    """UI 자산에 대한 HTTP 요청이 Inspector 저장소에 자체 수집되지 않는지 확인한다."""
    app = FastAPI()
    store = enable_inspector(app, prefix="/__tailora", enabled=True)
    client = TestClient(app)

    # 비즈니스 엔드포인트 정의
    @app.get("/api/hello")
    def hello():
        """Inspector 자체 요청과 구분할 테스트 응답을 반환한다."""
        return {"hello": "world"}

    # UI 자산 호출
    client.get("/__tailora")
    client.get("/__tailora/")
    client.get("/__tailora/styles.css")
    client.get("/__tailora/app.js")

    # 아직 비즈니스 요청을 하지 않았으므로 저장소는 비어 있어야 함
    assert store.size() == 0

    # 비즈니스 요청 실행
    client.get("/api/hello")
    assert store.size() == 1
    stored_event = store.list()[0]
    assert stored_event.route_template == "/api/hello"


def test_ui_custom_prefix_works():
    """커스텀 prefix를 지정했을 때도 UI가 올바른 base-path로 제공되는지 확인한다."""
    app = FastAPI()
    enable_inspector(app, prefix="/custom-inspector", enabled=True)
    client = TestClient(app)

    resp = client.get("/custom-inspector")
    assert resp.status_code == 200
    assert '<meta name="tailora-base-path" content="/custom-inspector">' in resp.text

    resp_js = client.get("/custom-inspector/app.js")
    assert resp_js.status_code == 200
