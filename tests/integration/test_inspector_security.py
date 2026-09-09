"""Inspector 활성화와 접근 제어의 FastAPI 통합 계약을 검증한다."""

import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import tailora.adapters.fastapi as fastapi_adapter
from tailora.adapters.fastapi import enable_inspector
from tailora.adapters.fastapi.middleware import TailoraMiddleware


def create_application() -> FastAPI:
    """보안 통합 테스트에 사용할 작은 FastAPI 앱을 만든다."""
    app = FastAPI(title="Security Test App")

    @app.get("/hello")
    def hello() -> dict[str, str]:
        """정상 수집 여부를 확인할 응답을 반환한다."""
        return {"message": "hello"}

    return app


def count_tailora_middleware(app: FastAPI) -> int:
    """앱에 등록된 Tailora 미들웨어 개수를 반환한다."""
    return sum(
        middleware.cls is TailoraMiddleware for middleware in app.user_middleware
    )


def test_default_enable_call_does_not_modify_application():
    """enabled를 명시하지 않으면 수집기와 API를 등록하지 않는다."""
    app = create_application()
    store = enable_inspector(app)
    client = TestClient(app)

    assert client.get("/__tailora/health").status_code == 404
    assert "TailoraSwaggerPlugin" not in client.get("/docs").text
    assert count_tailora_middleware(app) == 0

    client.get("/hello")
    assert store.size() == 0


def test_explicit_enable_turns_capture_api_and_plugin_on_together():
    """enabled=True를 지정하면 수집·API·Swagger plugin이 함께 켜진다."""
    app = create_application()
    store = enable_inspector(app, enabled=True)
    client = TestClient(app)

    assert client.get("/__tailora/health").status_code == 200
    assert "TailoraSwaggerPlugin" in client.get("/docs").text

    assert client.get("/hello").status_code == 200
    assert store.size() == 1


def test_path_prefix_keyword_configures_all_inspector_routes():
    """path_prefix 키워드가 API·UI·Swagger plugin 경로에 함께 적용된다."""
    app = create_application()
    enable_inspector(
        app,
        enabled=True,
        path_prefix="/diagnostics",
    )
    client = TestClient(app)

    assert client.get("/diagnostics/health").status_code == 200
    assert client.get("/__tailora/health").status_code == 404
    assert "/diagnostics/swagger-plugin.js" in client.get("/docs").text


def test_production_requires_second_confirmation_without_partial_registration():
    """production 활성화 확인이 없으면 앱을 변경하지 않고 거부한다."""
    app = create_application()
    original_routes = list(app.router.routes)

    with pytest.raises(ValueError, match="allow_in_production"):
        enable_inspector(
            app,
            enabled=True,
            environment="production",
        )

    assert app.router.routes == original_routes
    assert count_tailora_middleware(app) == 0


def test_confirmed_production_enable_emits_safe_warning(caplog):
    """이중 확인한 production 활성화가 안전한 경고를 남기는지 확인한다."""
    app = create_application()

    with caplog.at_level(logging.WARNING):
        enable_inspector(
            app,
            enabled=True,
            environment="production",
            allow_in_production=True,
        )

    assert "production" in caplog.text
    assert "authorization" not in caplog.text.lower()
    assert "token" not in caplog.text.lower()


def test_access_check_protects_all_endpoints_assets_and_plugin():
    """하나의 접근 hook이 API·UI·asset·Swagger plugin에 모두 적용된다."""

    def allow_with_header(request):
        """올바른 공유 개발용 헤더가 있는 요청만 허용한다."""
        return request.headers.get("x-inspector-access") == "allowed"

    app = create_application()
    enable_inspector(app, enabled=True, access_check=allow_with_header)
    client = TestClient(app)
    protected_paths = (
        "/__tailora/health",
        "/__tailora/requests",
        "/__tailora/aggregates",
        "/__tailora",
        "/__tailora/app.js",
        "/__tailora/swagger-plugin.js",
    )

    for path in protected_paths:
        assert client.get(path).status_code == 403

    denied_docs = client.get("/docs")
    assert denied_docs.status_code == 200
    assert "TailoraSwaggerPlugin" not in denied_docs.text

    headers = {"x-inspector-access": "allowed"}
    for path in protected_paths:
        assert client.get(path, headers=headers).status_code == 200

    allowed_docs = client.get("/docs", headers=headers)
    assert "TailoraSwaggerPlugin" in allowed_docs.text


def test_async_access_check_is_supported_by_api_and_docs():
    """비동기 접근 hook이 Inspector API와 Swagger 문서에서 동작한다."""

    async def allow_cookie(request):
        """테스트 쿠키가 있는 요청만 허용한다."""
        return request.cookies.get("inspector_session") == "allowed"

    app = create_application()
    enable_inspector(app, enabled=True, access_check=allow_cookie)
    client = TestClient(app)

    assert client.get("/__tailora/health").status_code == 403
    assert "TailoraSwaggerPlugin" not in client.get("/docs").text

    cookies = {"inspector_session": "allowed"}
    assert client.get("/__tailora/health", cookies=cookies).status_code == 200
    assert "TailoraSwaggerPlugin" in client.get("/docs", cookies=cookies).text


def test_duplicate_enable_with_same_settings_is_idempotent():
    """같은 설정으로 두 번 활성화해도 등록과 수집이 중복되지 않는다."""
    app = create_application()

    first_store = enable_inspector(app, enabled=True)
    second_store = enable_inspector(app, enabled=True)

    assert first_store is second_store
    assert count_tailora_middleware(app) == 1

    client = TestClient(app)
    client.get("/hello")
    assert first_store.size() == 1


def test_duplicate_enable_with_different_settings_is_rejected():
    """이미 켜진 앱에 다른 설정을 조용히 덮어쓰지 않는다."""
    app = create_application()
    enable_inspector(app, enabled=True)

    with pytest.raises(ValueError, match="different configuration"):
        enable_inspector(
            app,
            enabled=True,
            prefix="/diagnostics",
        )

    assert count_tailora_middleware(app) == 1


def test_path_collision_is_rejected_before_registration():
    """기존 라우트와 Inspector prefix가 겹치면 부분 등록 없이 거부한다."""
    app = create_application()

    @app.get("/diagnostics/health")
    def existing_diagnostics() -> dict[str, str]:
        """경로 충돌 테스트용 기존 라우트를 제공한다."""
        return {"status": "existing"}

    original_routes = list(app.router.routes)

    with pytest.raises(ValueError, match="path_prefix conflicts"):
        enable_inspector(
            app,
            enabled=True,
            prefix="/diagnostics",
        )

    assert app.router.routes == original_routes
    assert count_tailora_middleware(app) == 0


def test_catch_all_route_collision_is_rejected_before_registration():
    """기존 catch-all route가 Inspector prefix를 가리면 활성화를 거부한다."""
    app = FastAPI()

    @app.get("/{path:path}")
    def catch_all(path: str) -> dict[str, str]:
        """Inspector prefix를 가로채는 테스트용 catch-all 응답을 반환한다."""
        return {"caught": path}

    with pytest.raises(ValueError, match="path_prefix conflicts"):
        enable_inspector(
            app,
            enabled=True,
            path_prefix="/diagnostics",
        )

    assert count_tailora_middleware(app) == 0


def test_empty_list_excluded_paths_does_not_bypass_type_validation():
    """빈 list를 넘겨도 제외 경로의 tuple 자료형 검증을 우회하지 못한다."""
    app = create_application()

    with pytest.raises(ValueError, match="excluded_paths"):
        enable_inspector(
            app,
            enabled=True,
            excluded_paths=[],  # type: ignore[arg-type]
        )

    assert count_tailora_middleware(app) == 0


@pytest.mark.parametrize("dependencies", [False, [object()]])
def test_invalid_dependencies_are_rejected_before_registration(
    dependencies: object,
) -> None:
    """잘못된 인증 dependency 설정을 빈 설정으로 간주하지 않는다."""
    app = create_application()

    with pytest.raises(ValueError, match="dependencies"):
        enable_inspector(
            app,
            enabled=True,
            dependencies=dependencies,
        )

    assert count_tailora_middleware(app) == 0


def test_registration_failure_rolls_application_back(monkeypatch):
    """활성화 중 실패하면 route와 middleware를 등록 전 상태로 돌린다."""
    app = create_application()
    original_routes = list(app.router.routes)
    original_middleware = list(app.user_middleware)

    def fail_docs_install(application, inspector_prefix, access_check=None):
        """Swagger 등록 단계의 예외를 재현한다."""
        raise RuntimeError("docs install failed")

    monkeypatch.setattr(
        fastapi_adapter,
        "install_tailora_docs",
        fail_docs_install,
    )

    with pytest.raises(RuntimeError, match="docs install failed"):
        enable_inspector(app, enabled=True)

    assert app.router.routes == original_routes
    assert app.user_middleware == original_middleware
    assert not getattr(app.state, "_tailora_inspector_enabled", False)


def test_sensitive_request_and_response_values_are_not_collected():
    """요청·응답 본문과 인증 헤더의 원문이 이벤트에 저장되지 않는다."""
    app = FastAPI()

    @app.post("/echo")
    def echo(payload: dict[str, str]) -> dict[str, str]:
        """요청 본문의 비밀값을 응답으로 돌려준다."""
        return payload

    store = enable_inspector(app, enabled=True)
    client = TestClient(app)
    secret = "request-body-super-secret"

    response = client.post(
        "/echo?token=query-super-secret",
        headers={"Authorization": "Bearer header-super-secret"},
        json={"password": secret},
    )

    assert response.status_code == 200
    assert secret in response.text
    stored_text = repr(store.list()[0])
    assert "request-body-super-secret" not in stored_text
    assert "query-super-secret" not in stored_text
    assert "header-super-secret" not in stored_text


def test_invalid_engine_rolls_application_back():
    """SQLAlchemy Engine 검증이 실패해도 FastAPI 구성을 남기지 않는다."""
    app = create_application()
    original_routes = list(app.router.routes)

    with pytest.raises(TypeError, match="Engine"):
        enable_inspector(app, enabled=True, engine=object())

    assert app.router.routes == original_routes
    assert count_tailora_middleware(app) == 0
