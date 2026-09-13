"""FastAPI Inspector JSON API 엔드포인트의 동작을 확인한다."""

from collections.abc import Sequence
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, params
from fastapi.testclient import TestClient
import pytest

from tailora.adapters.fastapi import enable_inspector
from tailora.adapters.fastapi.api import create_inspector_router
from tailora.core.events import QueryEvent, RequestEvent
from tailora.core.policies import RedactionPolicy
from tailora.core.store import RingBuffer

EVENT_TIME = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)


def make_query(
    sequence: int = 1,
    statement: str = "SELECT * FROM users WHERE id = ?",
) -> QueryEvent:
    """테스트용 쿼리 이벤트를 생성한다."""
    return QueryEvent(
        query_id=f"q-{sequence}",
        sequence=sequence,
        started_at=EVENT_TIME,
        duration_ms=1.5,
        statement=statement,
        fingerprint="select * from users where id = ?",
        database="sqlite",
    )


def make_request(
    request_id: str,
    route_template: str = "/users",
    duration_ms: float = 10.0,
    queries: list[QueryEvent] | None = None,
) -> RequestEvent:
    """테스트용 요청 이벤트를 생성한다."""
    return RequestEvent(
        request_id=request_id,
        timestamp=EVENT_TIME,
        framework="fastapi",
        method="GET",
        route_template=route_template,
        status_code=200,
        duration_ms=duration_ms,
        queries=queries or [],
    )


def create_inspector_app(
    store: RingBuffer | None = None,
    excluded_paths: tuple[str, ...] | None = None,
    dependencies: Sequence[params.Depends] | None = None,
) -> tuple[FastAPI, RingBuffer]:
    """Inspector API가 활성화된 테스트용 FastAPI 앱을 생성한다."""
    app = FastAPI(title="Inspector Test App")
    resolved_store = enable_inspector(
        app,
        store=store,
        excluded_paths=excluded_paths,
        dependencies=dependencies,
        enabled=True,
    )
    return app, resolved_store


def test_health_endpoint():
    """health 엔드포인트가 Inspector 상태와 저장소 메타데이터를 반환하는지 확인한다."""
    store = RingBuffer(capacity=50)
    store.add(make_request("req-1"))
    app, _ = create_inspector_app(store=store)
    client = TestClient(app)

    response = client.get("/__tailora/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["stored_requests"] == 1
    assert data["capacity"] == 50


@pytest.mark.parametrize(
    "path",
    [
        "/__tailora/health",
        "/__tailora/requests",
        "/__tailora/requests/missing",
        "/__tailora/aggregates",
    ],
)
def test_inspector_data_responses_disable_caching(path: str):
    """Inspector 데이터 응답이 브라우저와 중간 캐시에 저장되지 않는지 확인한다."""
    app, _ = create_inspector_app()
    response = TestClient(app).get(path)

    assert response.headers["cache-control"] == "no-store"


def test_standalone_router_error_responses_disable_caching():
    """미들웨어 없이 등록한 Inspector router 오류 응답도 캐시되지 않게 한다."""

    def deny_request(request):
        """라우터 단독 사용 테스트에서 Inspector 접근을 거부한다."""
        return False

    denied_app = FastAPI()
    denied_app.include_router(
        create_inspector_router(
            RingBuffer(),
            access_check=deny_request,
        ),
    )
    denied_response = TestClient(denied_app).get("/__tailora/health")

    validation_app = FastAPI()
    validation_app.include_router(create_inspector_router(RingBuffer()))
    validation_response = TestClient(validation_app).get(
        "/__tailora/requests?limit=0",
    )

    assert denied_response.status_code == 403
    assert denied_response.headers["cache-control"] == "no-store"
    assert validation_response.status_code == 422
    assert validation_response.headers["cache-control"] == "no-store"


def test_requests_list_empty():
    """저장된 이벤트가 없을 때 빈 목록과 메타데이터를 반환하는지 확인한다."""
    app, _ = create_inspector_app()
    client = TestClient(app)

    response = client.get("/__tailora/requests")

    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["count"] == 0
    assert data["limit"] == 20
    assert data["total_stored_requests"] == 0
    assert data["is_truncated"] is False


def test_requests_list_ordered_and_limited():
    """최근 요청 목록이 최신순으로 정렬되고 limit이 적용되는지 확인한다."""
    store = RingBuffer()
    store.add(make_request("req-1", duration_ms=10.0))
    store.add(make_request("req-2", duration_ms=20.0, queries=[make_query(1)]))
    store.add(make_request("req-3", duration_ms=30.0))

    app, _ = create_inspector_app(store=store)
    client = TestClient(app)

    response = client.get("/__tailora/requests?limit=2")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert data["limit"] == 2

    items = data["items"]
    assert len(items) == 2
    assert items[0]["request_id"] == "req-3"
    assert items[1]["request_id"] == "req-2"
    assert items[1]["query_count"] == 1
    assert "queries" not in items[1]


def test_requests_list_passes_limit_to_store_snapshot():
    """목록 API가 요청한 개수만 저장소 snapshot으로 복사하는지 확인한다."""

    class TrackingStore(RingBuffer):
        """저장소 snapshot에 전달된 limit을 기록하는 테스트 저장소."""

        def __init__(self):
            """기록용 상태와 기본 링버퍼를 초기화한다."""
            super().__init__()
            self.requested_limits: list[int | None] = []

        def list(self, limit: int | None = None):
            """부모 snapshot을 호출하기 전에 요청된 limit을 기록한다."""
            self.requested_limits.append(limit)
            return super().list(limit)

    store = TrackingStore()
    store.add(make_request("req-1"))
    store.add(make_request("req-2"))
    app, _ = create_inspector_app(store=store)

    response = TestClient(app).get("/__tailora/requests?limit=1")

    assert response.status_code == 200
    assert store.requested_limits == [1]


def test_aggregates_use_read_only_store_view():
    """집계 API가 전체 이벤트 deep copy 대신 읽기 전용 뷰를 사용하는지 확인한다."""

    class TrackingStore(RingBuffer):
        """집계 API의 저장소 조회 방식을 기록하는 테스트 저장소."""

        def __init__(self):
            """조회 기록과 기본 링버퍼를 초기화한다."""
            super().__init__()
            self.view_limits: list[int | None] = []

        def _latest_view(self, limit: int | None = None):
            """읽기 전용 뷰 호출을 기록하고 부모 구현을 사용한다."""
            self.view_limits.append(limit)
            return super()._latest_view(limit)

        def list(self, limit: int | None = None):
            """집계 경로가 deep copy 목록을 사용하면 테스트를 실패시킨다."""
            raise AssertionError("aggregate must use latest_view")

    store = TrackingStore()
    store.add(make_request("req-1"))
    app, _ = create_inspector_app(store=store)

    response = TestClient(app).get("/__tailora/aggregates")

    assert response.status_code == 200
    assert store.view_limits == [None]


def test_requests_list_invalid_limit_returns_422():
    """잘못된 limit 파라미터 요청 시 422 오류를 반환하는지 확인한다."""
    app, _ = create_inspector_app()
    client = TestClient(app)

    assert client.get("/__tailora/requests?limit=0").status_code == 422
    assert client.get("/__tailora/requests?limit=-5").status_code == 422
    assert client.get("/__tailora/requests?limit=101").status_code == 422
    assert client.get("/__tailora/requests?limit=invalid").status_code == 422


def test_configured_store_and_api_limits_are_applied():
    """설정한 저장 용량과 API 기본·최대 결과 수가 전체 흐름에 적용된다."""
    app = FastAPI()
    store = enable_inspector(
        app,
        enabled=True,
        store_capacity=3,
        api_default_limit=1,
        api_max_limit=2,
    )
    for index in range(1, 4):
        query = make_query(index, statement=f"SELECT * FROM table_{index}")
        query.sequence = 1
        store.add(
            make_request(
                f"req-{index}",
                route_template=f"/route-{index}",
                queries=[query],
            ),
        )
    client = TestClient(app)

    health = client.get("/__tailora/health").json()
    requests = client.get("/__tailora/requests").json()
    aggregates = client.get("/__tailora/aggregates").json()

    assert health["capacity"] == 3
    assert requests["count"] == 1
    assert requests["limit"] == 1
    assert requests["total_stored_requests"] == 3
    assert requests["is_truncated"] is True
    assert client.get("/__tailora/requests?limit=3").status_code == 422
    assert len(aggregates["routes"]) == 1
    assert len(aggregates["fingerprints"]) == 1
    assert aggregates["is_routes_truncated"] is True
    assert aggregates["is_fingerprints_truncated"] is True
    assert aggregates["analysis_scope"]["request_count"] == 3


def test_request_detail_found():
    """존재하는 요청 ID로 조회 시 쿼리를 포함한 전체 상세 정보를 반환하는지 확인한다."""
    store = RingBuffer()
    store.add(make_request("req-target", queries=[make_query(1)]))
    app, _ = create_inspector_app(store=store)
    client = TestClient(app)

    response = client.get("/__tailora/requests/req-target")

    assert response.status_code == 200
    data = response.json()
    assert data["request_id"] == "req-target"
    assert data["query_count"] == 1
    assert len(data["queries"]) == 1
    assert data["queries"][0]["statement"] == "SELECT * FROM users WHERE id = ?"


def test_request_detail_not_found():
    """존재하지 않는 요청 ID로 조회 시 404 오류를 반환하는지 확인한다."""
    app, _ = create_inspector_app()
    client = TestClient(app)

    response = client.get("/__tailora/requests/nonexistent-id")

    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "request_not_found"
    assert "not found" in data["error"]["message"].lower()


def test_request_detail_not_found_does_not_echo_sensitive_id():
    """요청 ID에 민감한 값이 있어도 404 응답에 되돌려주지 않는다."""
    app, _ = create_inspector_app()
    client = TestClient(app)

    response = client.get("/__tailora/requests/token=super-secret")

    assert response.status_code == 404
    assert "super-secret" not in response.text


def test_request_detail_with_invalid_whitespace_id_returns_safe_not_found():
    """공백 request ID가 내부 예외 대신 안전한 404를 반환하는지 확인한다."""
    app, _ = create_inspector_app()
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/__tailora/requests/%20")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "request_not_found"


def test_aggregates_endpoint():
    """기본 집계 엔드포인트가 라우트와 Fingerprint 통계를 반환하는지 확인한다."""
    store = RingBuffer()
    store.add(make_request("req-1", route_template="/users", queries=[make_query(1)]))
    store.add(make_request("req-2", route_template="/users", queries=[make_query(1)]))
    app, _ = create_inspector_app(store=store)
    client = TestClient(app)

    response = client.get("/__tailora/aggregates")

    assert response.status_code == 200
    data = response.json()
    assert "routes" in data
    assert "fingerprints" in data
    assert len(data["routes"]) == 1
    assert data["routes"][0]["route_template"] == "/users"
    assert data["routes"][0]["count"] == 2
    assert len(data["fingerprints"]) == 1
    assert data["fingerprints"][0]["count"] == 2
    assert data["analysis_scope"] == {
        "request_count": 2,
        "analyzed_query_count": 2,
        "total_query_count": 2,
        "is_queries_truncated": False,
    }


def test_inspector_api_requests_not_captured_even_with_custom_excluded_paths():
    """커스텀 제외 경로 지정 시에도 Inspector 요청이 수집되지 않음을 확인한다."""
    app, store = create_inspector_app(excluded_paths=("/custom-ignore",))
    client = TestClient(app)

    client.get("/__tailora/health")
    client.get("/__tailora/requests")
    client.get("/__tailora/aggregates")

    assert store.size() == 0


def test_disabled_inspector_does_not_expose_routes():
    """비활성 상태에서는 Inspector 라우트가 노출되지 않는지 확인한다."""
    app = FastAPI()
    client = TestClient(app)

    assert client.get("/__tailora/health").status_code == 404
    assert client.get("/__tailora/requests").status_code == 404


def test_api_layer_enforces_redaction_defense_in_depth():
    """저장소에 원문 SQL이 직접 삽입되어 있어도 API 계층에서 마스킹되는지 확인한다."""
    store = RingBuffer()
    # 저장소에 마스킹되지 않은 원문 쿼리를 직접 삽입
    unredacted_query = make_query(
        1,
        statement="SELECT * FROM users WHERE password = 'super-secret-value'",
    )
    store.add(make_request("req-secret", queries=[unredacted_query]))

    app, _ = create_inspector_app(store=store)
    client = TestClient(app)

    response = client.get("/__tailora/requests/req-secret")
    assert response.status_code == 200
    data = response.json()
    assert "super-secret-value" not in data["queries"][0]["statement"]
    assert data["queries"][0]["statement"] == "SELECT * FROM users WHERE password = ?"


def test_inspector_api_with_authentication_dependency():
    """인증 dependency를 주입하여 비인가 접근을 차단할 수 있는지 확인한다."""

    def verify_token(api_key: str | None = None) -> None:
        """테스트용 API 키 검증 의존성."""
        if api_key != "secret-token":
            raise HTTPException(status_code=401, detail="Unauthorized")

    app = FastAPI()
    enable_inspector(
        app,
        dependencies=[Depends(verify_token)],
        enabled=True,
    )
    client = TestClient(app)

    # 인증 없이 요청 -> 401
    resp_unauth = client.get("/__tailora/health")
    assert resp_unauth.status_code == 401

    # 올바른 키로 요청 -> 200
    resp_auth = client.get("/__tailora/health?api_key=secret-token")
    assert resp_auth.status_code == 200


def test_enable_inspector_idempotent():
    """enable_inspector를 중복 호출해도 중복 등록되지 않는지 확인한다."""
    app = FastAPI()

    @app.get("/hello")
    def hello() -> dict[str, str]:
        """테스트용 엔드포인트."""
        return {"msg": "hello"}

    store1 = enable_inspector(app, enabled=True)
    store2 = enable_inspector(app, enabled=True)

    assert store1 is store2

    client = TestClient(app)
    resp = client.get("/hello")
    assert resp.status_code == 200

    # 중복 미들웨어로 인해 2개가 쌓이지 않고 정확히 1개만 쌓여야 함
    assert store1.size() == 1


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"prefix": "/unsafe/../path"}, "path_prefix"),
        ({"default_limit": 0}, "api_default_limit"),
        (
            {"default_limit": 2, "max_limit": 1},
            "api_default_limit",
        ),
        (
            {"policy": RedactionPolicy(enabled=False)},
            "redaction_policy",
        ),
        ({"policy": False}, "redaction_policy"),
        ({"threshold_policy": False}, "threshold_policy"),
    ],
)
def test_create_inspector_router_validates_public_configuration(
    kwargs: dict[str, object],
    message: str,
) -> None:
    """라우터를 직접 생성해도 공통 보안 설정 검증을 적용하는지 확인한다."""
    with pytest.raises(ValueError, match=message):
        create_inspector_router(RingBuffer(), **kwargs)


def test_create_inspector_router_requires_ring_buffer() -> None:
    """공개 라우터 생성 함수가 잘못된 저장소 자료형을 즉시 거부한다."""
    with pytest.raises(TypeError, match="store"):
        create_inspector_router(object())
