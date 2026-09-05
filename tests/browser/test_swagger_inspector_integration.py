"""Swagger UI 안에서 Tailora Inspector 탭이 동작하는지 브라우저로 검증한다."""

from playwright.sync_api import Page, Route, expect


def abort_plugin_request(route: Route) -> None:
    """플러그인 JavaScript 요청을 중단해 fallback 동작을 검증한다."""
    route.abort()


def test_docs_and_inspector_tabs_work_together(
    browser_page: Page,
    live_example_url: str,
) -> None:
    """API Docs 상태를 유지한 채 Inspector에서 수집한 요청을 볼 수 있는지 확인한다."""
    page = browser_page
    page.goto(f"{live_example_url}/users/1")
    expect(page.locator("body")).to_contain_text("Alice")

    page.goto(f"{live_example_url}/docs")
    docs_tab = page.get_by_role("tab", name="API Docs")
    inspector_tab = page.get_by_role("tab", name="Inspector")

    expect(docs_tab).to_have_attribute("aria-selected", "true")
    expect(inspector_tab).to_have_attribute("aria-selected", "false")
    user_operation = page.locator(".opblock").filter(
        has_text="/users/{user_id}",
    )
    user_operation.get_by_role(
        "button",
        name="GET /users/{user_id} Get User",
    ).click()
    try_it_out_button = user_operation.get_by_role("button", name="Try it out")
    expect(try_it_out_button).to_be_visible()
    try_it_out_button.click()
    user_operation.locator("input").first.fill("1")
    user_operation.get_by_role("button", name="Execute").click()
    expect(user_operation.get_by_text("200").first).to_be_visible()

    docs_tab.focus()
    docs_tab.press("ArrowRight")
    inspector_frame = page.frame_locator("iframe[title='Tailora Inspector']")

    expect(inspector_tab).to_have_attribute("aria-selected", "true")
    expect(
        inspector_frame.get_by_role("heading", name="Tailora Inspector"),
    ).to_be_visible()
    expect(
        inspector_frame.get_by_role("option")
        .filter(
            has_text="/users/{user_id}",
        )
        .first,
    ).to_be_visible()

    docs_tab.click()

    expect(docs_tab).to_have_attribute("aria-selected", "true")
    expect(user_operation.get_by_role("button", name="Execute")).to_be_visible()
    expect(user_operation.get_by_role("textbox", name="user_id")).to_have_value("1")


def test_plugin_asset_failure_keeps_api_docs_available(
    browser_page: Page,
    live_example_url: str,
) -> None:
    """Swagger plugin 자산을 불러오지 못해도 기본 API Docs가 보이는지 확인한다."""
    page = browser_page
    page.route("**/swagger-plugin.js", abort_plugin_request)

    page.goto(f"{live_example_url}/docs")

    warning = page.get_by_role("status")
    expect(warning).to_contain_text("Inspector를 불러오지 못했습니다")
    expect(
        page.get_by_role("button", name="GET /users/{user_id} Get User"),
    ).to_be_visible()


def test_inspector_is_loaded_only_after_its_tab_is_selected(
    browser_page: Page,
    live_example_url: str,
) -> None:
    """Inspector 선택 전에는 화면과 API를 요청하지 않는지 확인한다."""
    page = browser_page
    inspector_requests: list[str] = []

    def record_inspector_request(request) -> None:
        """Inspector 화면과 API 요청만 별도로 기록한다."""
        if request.url.startswith(f"{live_example_url}/__tailora/"):
            inspector_requests.append(request.url)

    page.on("request", record_inspector_request)
    page.goto(f"{live_example_url}/docs", wait_until="networkidle")

    expect(page.locator("iframe[title='Tailora Inspector']")).to_have_count(0)
    assert inspector_requests == [
        f"{live_example_url}/__tailora/swagger-plugin.css",
        f"{live_example_url}/__tailora/swagger-plugin.js",
    ]

    page.get_by_role("tab", name="Inspector").click()

    expect(
        page.frame_locator("iframe[title='Tailora Inspector']").get_by_role(
            "heading",
            name="Tailora Inspector",
        ),
    ).to_be_visible()
    assert f"{live_example_url}/__tailora/health" in inspector_requests
    assert f"{live_example_url}/__tailora/requests?limit=20" in inspector_requests


def test_inspector_tab_is_usable_in_a_narrow_viewport(
    browser_page: Page,
    live_example_url: str,
) -> None:
    """좁은 화면에서도 API Docs와 Inspector 탭을 선택할 수 있는지 확인한다."""
    page = browser_page
    page.set_viewport_size({"width": 390, "height": 844})

    page.goto(f"{live_example_url}/docs")
    inspector_tab = page.get_by_role("tab", name="Inspector")

    expect(inspector_tab).to_be_visible()
    inspector_tab.click()
    expect(
        page.frame_locator("iframe[title='Tailora Inspector']").get_by_role(
            "heading",
            name="Tailora Inspector",
        ),
    ).to_be_visible()
