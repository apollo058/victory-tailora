"""Chromium에서 Inspector의 문자열 렌더링과 스크립트 차단을 확인한다."""

from urllib.parse import urlsplit

from playwright.sync_api import Page, Route, expect


def test_inspector_does_not_interpret_event_strings_as_html(
    browser_page: Page,
    live_example_url: str,
) -> None:
    """모든 표시 문자열에 HTML 공격값을 넣어도 DOM 요소나 이벤트를 만들지 않는다."""
    page = browser_page
    handler = "".join(f"&#{ord(char)};" for char in "window.__tailoraXss=1")
    payload = f'<img src=x onerror="{handler}">'
    method = 'GET">' + payload
    detail = {
        "request_id": "safe-id",
        "timestamp": "2026-10-13T00:00:00Z",
        "framework": payload,
        "method": method,
        "route_template": payload,
        "status_code": 200,
        "duration_ms": 1.0,
        "query_count": 1,
        "query_time_ms": 1.0,
        "error": {"type": payload, "message": payload},
        "signals": {},
        "queries": [
            {
                "sequence": 1,
                "duration_ms": 1.0,
                "database": payload,
                "statement": payload,
                "fingerprint": payload,
            }
        ],
    }

    def dashboard_response(route: Route) -> None:
        route.fulfill(json={"items": [detail]})

    page.route("**/__tailora/requests", dashboard_response)
    page.route(
        "**/__tailora/requests/safe-id", lambda route: route.fulfill(json=detail)
    )
    page.goto(f"{live_example_url}/__tailora")
    expect(page.locator(".request-item")).to_be_visible()
    page.locator(".request-item").click()
    expect(page.locator(".query-sql")).to_have_text(payload)
    expect(page.locator(".method-tag")).to_have_text(method.upper())
    assert page.locator("img").count() == 0
    assert page.evaluate("window.__tailoraXss || 0") == 0


def test_inspector_csp_blocks_inline_scripts(browser_page: Page, live_example_url: str):
    """HTML에 들어온 inline script도 Inspector CSP가 실행하지 않는다."""
    page = browser_page
    response = page.goto(f"{live_example_url}/__tailora")
    assert response is not None
    assert "script-src 'self'" in response.headers["content-security-policy"]
    page.evaluate("""() => {
      const script = document.createElement('script');
      script.textContent = 'window.__tailoraInlineScript = 1';
      document.body.appendChild(script);
    }""")
    assert page.evaluate("window.__tailoraInlineScript || 0") == 0


def test_swagger_query_cannot_replace_the_schema_or_enable_external_validation(
    browser_page: Page,
    live_example_url: str,
):
    """문서 URL의 쿼리로 외부 schema/validator를 지정할 수 없다."""
    page = browser_page
    external_requests = []
    page.on(
        "request",
        lambda request: (
            external_requests.append(request.url)
            if urlsplit(request.url).hostname
            in {
                "attacker.example",
                "validator.swagger.io",
            }
            else None
        ),
    )
    page.goto(
        f"{live_example_url}/docs?url=https://attacker.example/schema.json"
        "&validatorUrl=https://attacker.example/validate",
    )
    expect(page.get_by_role("tab", name="Inspector")).to_be_visible()
    expect(page.locator(".opblock").filter(has_text="/users/{user_id}")).to_be_visible()
    config = page.evaluate("window.ui.getConfigs()")
    assert config["queryConfigEnabled"] is False
    assert config["validatorUrl"] is None
    assert config["persistAuthorization"] is False
    assert external_requests == []
