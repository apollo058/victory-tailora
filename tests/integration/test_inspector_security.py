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
    client = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))

    assert client.get("/__tailora/health").status_code == 404
    assert "TailoraSwaggerPlugin" not in client.get("/docs").text
    assert count_tailora_middleware(app) == 0

    client.get("/hello")
    assert store.size() == 0


def test_enabled_inspector_with_unspecified_environment_requires_authentication():
    """환경을 누락해도 로컬로 간주하여 인증 없는 API를 등록하지 않는다."""
    app = create_application()
    original_routes = list(app.router.routes)
    with pytest.raises(ValueError, match="access_check"):
        enable_inspector(app, enabled=True)
    assert app.router.routes == original_routes
    assert count_tailora_middleware(app) == 0


@pytest.mark.parametrize(
    ("client_host", "host", "expected_status"),
    [
        ("127.0.0.1", "localhost", 200),
        ("127.0.0.1", "127.0.0.1:8000", 200),
        ("::1", "[::1]:8000", 200),
        ("203.0.113.1", "localhost", 403),
        ("127.0.0.1", "attacker.example", 403),
        ("127.0.0.1", "localhost.attacker.example", 403),
        ("127.0.0.1", "localhost@attacker.example", 403),
        ("127.0.0.1", "localhost:invalid", 403),
        ("127.0.0.1", "localhost:99999", 403),
        ("127.0.0.1", "localhost\\attacker.example", 403),
    ],
)
def test_unauthenticated_local_inspector_checks_client_and_host(
    client_host,
    host,
    expected_status,
):
    """로컬 모드에서 외부 클라이언트와 DNS rebinding Host를 거부한다."""
    app = create_application()
    enable_inspector(app, enabled=True, environment="development")
    client = TestClient(app, base_url="http://localhost", client=(client_host, 50000))
    response = client.get("/__tailora/health", headers={"host": host})
    assert response.status_code == expected_status
    docs = client.get("/docs", headers={"host": host})
    assert ("TailoraSwaggerPlugin" in docs.text) is (expected_status == 200)


def test_forwarded_headers_do_not_authorize_a_remote_local_mode_request():
    """직접 전달한 proxy 헤더를 인증 없는 로컬 접근의 근거로 사용하지 않는다."""
    app = create_application()
    enable_inspector(app, enabled=True, environment="development")
    client = TestClient(app, base_url="http://localhost", client=("203.0.113.1", 50000))
    response = client.get(
        "/__tailora/requests",
        headers={"x-forwarded-for": "127.0.0.1", "x-forwarded-host": "localhost"},
    )
    assert response.status_code == 403


def test_duplicate_host_headers_are_denied_in_local_mode():
    """여러 Host의 해석 차이로 로컬 검사를 우회하지 못한다."""
    app = create_application()
    enable_inspector(app, enabled=True, environment="development")
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
    response = client.get(
        "/__tailora/health",
        headers=[("host", "localhost"), ("host", "attacker.example")],
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    ("headers", "expected_status"),
    [
        ({"origin": "http://localhost"}, 200),
        ({"origin": "https://localhost"}, 403),
        ({"origin": "http://localhost:3000"}, 403),
        ({"origin": "http://localhost:0"}, 403),
        ({"origin": "https://attacker.example"}, 403),
        ({"origin": "null"}, 403),
        ({"origin": "http://localhost@attacker.example"}, 403),
        ({"sec-fetch-site": "cross-site"}, 403),
    ],
)
def test_local_access_denies_other_origins_even_when_host_cors_is_permissive(
    headers,
    expected_status,
):
    """호스트 앱 CORS가 넓어도 다른 origin에 로컬 Inspector 데이터를 제공하지 않는다."""
    from fastapi.middleware.cors import CORSMiddleware

    app = create_application()
    enable_inspector(app, enabled=True, environment="development")
    app.add_middleware(CORSMiddleware, allow_origins=["*"])
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
    response = client.get("/__tailora/requests", headers=headers)
    assert response.status_code == expected_status
    if expected_status != 200:
        assert '"items"' not in response.text


def test_authenticated_inspector_can_serve_a_remote_request():
    """정상 인증한 공유 환경의 클라이언트는 loopback 제한을 받지 않는다."""
    app = create_application()
    enable_inspector(app, enabled=True, access_check=lambda request: True)
    client = TestClient(
        app, base_url="https://app.example", client=("203.0.113.1", 50000)
    )
    assert client.get("/__tailora/health").status_code == 200


def test_inspector_ui_response_has_script_and_frame_protection():
    """Inspector iframe에는 동일 origin의 외부 스크립트만 허용한다."""
    app = create_application()
    enable_inspector(app, enabled=True, access_check=lambda request: True)
    response = TestClient(app).get("/__tailora")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "SAMEORIGIN"
    policy = response.headers["content-security-policy"]
    assert "script-src 'self';" in policy
    assert "frame-ancestors 'self'" in policy


@pytest.mark.parametrize(
    "path",
    [
        "/__tailora/health",
        "/__tailora/requests?limit=invalid",
        "/__tailora/aggregates?limit=1000000",
        "/__tailora/requests/unknown-id",
        "/__tailora/index.html",
        "/__tailora/styles.css",
        "/__tailora/swagger-plugin.css",
        "/%5f%5ftailora/requests",
        "/__tailora/ignored/../app.js",
        "/__tailora/%2e%2e/loader.py",
    ],
)
def test_denied_access_cannot_be_bypassed_with_path_or_validation_inputs(path):
    """경로 인코딩·정규화·잘못된 입력으로 데이터나 자산 인증을 우회하지 못한다."""
    app = create_application()
    enable_inspector(app, enabled=True, access_check=lambda request: False)
    response = TestClient(
        app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)
    ).get(path)
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    assert "<!doctype" not in response.text.lower()
    assert "stored_requests" not in response.text


def test_explicit_enable_turns_capture_api_and_plugin_on_together():
    """enabled=True를 지정하면 수집·API·Swagger plugin이 함께 켜진다."""
    app = create_application()
    store = enable_inspector(app, enabled=True, environment="development")
    client = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))

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
        environment="development",
        path_prefix="/diagnostics",
    )
    client = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))

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

    def allow_production_request(request):
        """production Inspector 테스트 요청을 허용한다."""
        return True

    with caplog.at_level(logging.WARNING):
        enable_inspector(
            app,
            enabled=True,
            environment="production",
            allow_in_production=True,
            access_check=allow_production_request,
        )

    assert "production" in caplog.text
    assert "authorization" not in caplog.text.lower()
    assert "token" not in caplog.text.lower()


def test_production_requires_access_check_before_registration():
    """production Inspector가 접근 hook 없이 활성화되지 않는지 확인한다."""
    app = create_application()
    original_routes = list(app.router.routes)

    with pytest.raises(ValueError, match="access_check"):
        enable_inspector(
            app,
            enabled=True,
            environment="production",
            allow_in_production=True,
        )

    assert app.router.routes == original_routes
    assert count_tailora_middleware(app) == 0


@pytest.mark.parametrize("environment", ["staging", "stage", "preprod"])
def test_shared_environment_requires_access_check_before_registration(environment):
    """공유·검증 환경은 접근 제어 없이 Inspector를 켜지 못하게 한다."""
    app = create_application()
    original_routes = list(app.router.routes)

    with pytest.raises(ValueError, match="access_check"):
        enable_inspector(
            app,
            enabled=True,
            environment=environment,
        )

    assert app.router.routes == original_routes
    assert count_tailora_middleware(app) == 0


def test_shared_environment_accepts_authentication_dependency(caplog):
    """공유 환경은 명시적으로 전달한 인증 dependency를 사용할 수 있다."""
    from fastapi import Depends, HTTPException

    def require_key(api_key: str | None = None) -> None:
        """테스트용 인증 키가 없으면 요청을 거부한다."""
        if api_key != "test-key":
            raise HTTPException(status_code=401)

    app = create_application()
    with caplog.at_level(logging.INFO):
        enable_inspector(
            app,
            enabled=True,
            environment="staging",
            dependencies=[Depends(require_key)],
        )

    client = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
    assert client.get("/__tailora/health").status_code == 401
    assert client.get("/__tailora/health?api_key=test-key").status_code == 200
    assert "access_control=True" in caplog.text
    assert "no access control" not in caplog.text.lower()


def test_access_check_protects_all_endpoints_assets_and_plugin():
    """하나의 접근 hook이 API·UI·asset·Swagger plugin에 모두 적용된다."""

    def allow_with_header(request):
        """올바른 공유 개발용 헤더가 있는 요청만 허용한다."""
        return request.headers.get("x-inspector-access") == "allowed"

    app = create_application()
    enable_inspector(
        app, enabled=True, environment="development", access_check=allow_with_header
    )
    client = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
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


def test_denied_inspector_response_disables_caching():
    """접근 거부 응답도 중간 캐시에 저장되지 않는지 확인한다."""

    def deny_request(request):
        """테스트 요청을 항상 거부한다."""
        return False

    app = create_application()
    enable_inspector(
        app, enabled=True, environment="development", access_check=deny_request
    )

    response = TestClient(
        app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)
    ).get("/__tailora/health")

    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"


def test_async_access_check_is_supported_by_api_and_docs():
    """비동기 접근 hook이 Inspector API와 Swagger 문서에서 동작한다."""

    async def allow_cookie(request):
        """테스트 쿠키가 있는 요청만 허용한다."""
        return request.cookies.get("inspector_session") == "allowed"

    app = create_application()
    enable_inspector(
        app, enabled=True, environment="development", access_check=allow_cookie
    )
    client = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))

    assert client.get("/__tailora/health").status_code == 403
    assert "TailoraSwaggerPlugin" not in client.get("/docs").text

    cookies = {"inspector_session": "allowed"}
    assert client.get("/__tailora/health", cookies=cookies).status_code == 200
    assert "TailoraSwaggerPlugin" in client.get("/docs", cookies=cookies).text


def test_duplicate_enable_with_same_settings_is_idempotent():
    """같은 설정으로 두 번 활성화해도 등록과 수집이 중복되지 않는다."""
    app = create_application()

    first_store = enable_inspector(app, enabled=True, environment="development")
    second_store = enable_inspector(app, enabled=True, environment="development")

    assert first_store is second_store
    assert count_tailora_middleware(app) == 1

    client = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
    client.get("/hello")
    assert first_store.size() == 1


def test_duplicate_enable_with_different_settings_is_rejected():
    """이미 켜진 앱에 다른 설정을 조용히 덮어쓰지 않는다."""
    app = create_application()
    enable_inspector(app, enabled=True, environment="development")

    with pytest.raises(ValueError, match="different configuration"):
        enable_inspector(
            app,
            enabled=True,
            environment="development",
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
            environment="development",
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
            environment="development",
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
            environment="development",
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
            environment="development",
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
        enable_inspector(app, enabled=True, environment="development")

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

    store = enable_inspector(app, enabled=True, environment="development")
    client = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
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
        enable_inspector(app, enabled=True, environment="development", engine=object())

    assert app.router.routes == original_routes
    assert count_tailora_middleware(app) == 0
