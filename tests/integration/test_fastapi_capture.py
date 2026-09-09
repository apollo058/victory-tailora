"""FastAPI 요청 수집 미들웨어의 동작을 확인한다."""

import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import httpx
import pytest

from tailora.adapters.fastapi.middleware import TailoraMiddleware
from tailora.core.context import record_query
from tailora.core.events import QueryEvent, RequestEvent
from tailora.core.policies import RedactionPolicy
from tailora.core.store import RingBuffer

EVENT_TIME = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)


def make_query(sequence: int = 1, statement: str = "SELECT 1") -> QueryEvent:
    """테스트용 쿼리 이벤트를 만든다."""
    return QueryEvent(
        query_id=f"q-{sequence}",
        sequence=sequence,
        started_at=EVENT_TIME,
        duration_ms=1.5,
        statement=statement,
    )


def _register_success_routes(app: FastAPI) -> None:
    """정상 응답과 쿼리 수집을 검증할 라우트를 등록한다."""
    @app.get("/health")
    def health_check() -> dict[str, str]:
        """정상 동작 확인용 헬스체크 엔드포인트."""
        return {"status": "ok"}

    @app.get("/users/{user_id}")
    def get_user(user_id: int) -> dict[str, int]:
        """사용자 조회 및 쿼리 기록 엔드포인트."""
        record_query(make_query(1, "SELECT * FROM users WHERE id = 42"))
        return {"user_id": user_id}


def _register_error_routes(app: FastAPI) -> None:
    """HTTP 및 서버 오류 수집을 검증할 라우트를 등록한다."""
    @app.get("/not-found")
    def not_found_route() -> None:
        """404 HTTPException을 발생하는 엔드포인트."""
        raise HTTPException(status_code=404, detail="Item not found")

    @app.get("/teapot")
    def teapot_route() -> None:
        """418 HTTPException을 발생하는 엔드포인트."""
        raise HTTPException(status_code=418, detail="I am a teapot")

    @app.get("/secret-error")
    def secret_error_route() -> None:
        """민감정보가 포함된 detail을 던지는 엔드포인트."""
        raise HTTPException(
            status_code=400,
            detail={
                "password": "super-secret-value",
                "token": "abc123secret",
                "msg": "Invalid token provided",
            },
        )

    @app.get("/crash")
    def crash_route() -> None:
        """처리되지 않은 500 예외를 발생하는 엔드포인트."""
        raise RuntimeError("Something went wrong")


def _register_internal_routes(app: FastAPI) -> None:
    """쿼리 보정과 Inspector 제외 경로를 검증할 라우트를 등록한다."""
    @app.get("/broken-query-sequence")
    def broken_query_route() -> dict[str, str]:
        """순서가 잘못된 쿼리를 강제로 기록하는 엔드포인트."""
        # 1번 없이 99번 시퀀스 쿼리 기록
        record_query(make_query(99, "SELECT 99"))
        return {"status": "broken_query_recorded"}

    @app.get("/__tailora/health")
    def internal_health() -> dict[str, str]:
        """수집 제외 대상인 Inspector 내부 엔드포인트."""
        return {"inspector": "ok"}


def create_test_app(
    store: RingBuffer | None = None,
    enabled: bool = True,
    policy: RedactionPolicy | None = None,
) -> FastAPI:
    """테스트용 FastAPI 앱과 Tailora 미들웨어를 구성한다."""
    app = FastAPI(title="Test App")
    _register_success_routes(app)
    _register_error_routes(app)
    _register_internal_routes(app)
    app.add_middleware(
        TailoraMiddleware,
        store=store,
        policy=policy,
        enabled=enabled,
    )
    return app


def test_default_middleware_is_disabled():
    """미들웨어의 enabled 기본값이 False여서 기본적으로 수집하지 않는지 확인한다."""
    app = FastAPI()

    @app.get("/ping")
    def ping() -> dict[str, str]:
        """핑 응답 엔드포인트."""
        return {"ping": "pong"}

    store = RingBuffer()
    app.add_middleware(TailoraMiddleware, store=store)
    client = TestClient(app)

    response = client.get("/ping")

    assert response.status_code == 200
    assert store.size() == 0


def test_successful_request_captured():
    """정상 요청이 링버퍼에 RequestEvent로 저장되는지 확인한다."""
    store = RingBuffer()
    app = create_test_app(store=store, enabled=True)
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert store.size() == 1

    events = store.list()
    event = events[0]
    assert event.framework == "fastapi"
    assert event.method == "GET"
    assert event.route_template == "/health"
    assert event.status_code == 200
    assert event.duration_ms >= 0
    assert event.query_count == 0
    assert event.error is None


def test_route_template_and_queries_captured():
    """경로 매개변수가 포함된 템플릿과 쿼리가 함께 저장되는지 확인한다."""
    store = RingBuffer()
    app = create_test_app(store=store, enabled=True)
    client = TestClient(app)

    response = client.get("/users/42")

    assert response.status_code == 200
    assert response.json() == {"user_id": 42}
    assert store.size() == 1

    event = store.list()[0]
    assert event.route_template == "/users/{user_id}"
    assert event.query_count == 1
    assert event.query_time_ms == 1.5
    assert event.queries[0].statement == "SELECT * FROM users WHERE id = ?"


def test_http_exception_captured_with_error_summary():
    """HTTPException 발생 시 상태 코드와 에러 요약이 저장되는지 확인한다."""
    store = RingBuffer()
    app = create_test_app(store=store, enabled=True)
    client = TestClient(app)

    response_404 = client.get("/not-found")
    assert response_404.status_code == 404
    assert store.size() == 1

    event_404 = store.list()[0]
    assert event_404.route_template == "/not-found"
    assert event_404.status_code == 404
    assert event_404.error is not None
    assert event_404.error.type == "HTTPException"
    assert event_404.error.message == "Item not found"

    response_418 = client.get("/teapot")
    assert response_418.status_code == 418
    assert store.size() == 2

    event_418 = store.list()[0]
    assert event_418.route_template == "/teapot"
    assert event_418.status_code == 418
    assert event_418.error is not None
    assert event_418.error.type == "HTTPException"
    assert event_418.error.message == "I am a teapot"


def test_http_exception_with_sensitive_detail_redacted():
    """HTTP 에러 detail에 포함된 민감정보가 안전하게 마스킹되는지 확인한다."""
    store = RingBuffer()
    app = create_test_app(store=store, enabled=True)
    client = TestClient(app)

    response = client.get("/secret-error")
    assert response.status_code == 400
    assert store.size() == 1

    event = store.list()[0]
    assert event.error is not None
    assert event.error.type == "HTTPException"
    assert "super-secret-value" not in (event.error.message or "")
    assert "abc123secret" not in (event.error.message or "")
    assert "Invalid token provided" in (event.error.message or "")


def test_unhandled_exception_captured_and_reraised():
    """처리되지 않은 예외 발생 시 500으로 기록되고 에러 요약이 저장되는지 확인한다."""
    store = RingBuffer()
    app = create_test_app(store=store, enabled=True)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/crash")

    assert response.status_code == 500
    assert store.size() == 1

    event = store.list()[0]
    assert event.route_template == "/crash"
    assert event.status_code == 500
    assert event.error is not None
    assert event.error.type == "RuntimeError"
    assert "Something went wrong" in (event.error.message or "")


def test_excluded_paths_not_captured():
    """제외 경로(/__tailora) 요청은 링버퍼에 저장되지 않는지 확인한다."""
    store = RingBuffer()
    app = create_test_app(store=store, enabled=True)
    client = TestClient(app)

    response = client.get("/__tailora/health")

    assert response.status_code == 200
    assert store.size() == 0


def test_disabled_middleware_does_not_capture():
    """미들웨어가 비활성화되었을 때 요청이 저장되지 않는지 확인한다."""
    store = RingBuffer()
    app = create_test_app(store=store, enabled=False)
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert store.size() == 0


def test_collector_error_does_not_break_api_response(caplog):
    """수집 실패가 API를 깨뜨리거나 민감한 로그를 남기지 않는다."""

    class BrokenStore(RingBuffer):
        """이벤트 추가 시 의도적으로 실패하는 저장소."""

        def add(self, event: RequestEvent) -> None:
            """의도적으로 예외를 던진다."""
            raise RuntimeError("Storage failure token=super-secret")

    app = create_test_app(store=BrokenStore(), enabled=True)
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "Tailora event collection failed" in caplog.text
    assert "super-secret" not in caplog.text


def test_query_limit_is_applied_during_request_capture():
    """요청 처리 중 쿼리 상한을 적용하면서 전체 실행 수를 보존한다."""
    app = FastAPI()
    store = RingBuffer()
    policy = RedactionPolicy(max_queries_per_request=1)
    app.add_middleware(
        TailoraMiddleware,
        store=store,
        policy=policy,
        enabled=True,
    )

    @app.get("/many-queries")
    def many_queries() -> dict[str, bool]:
        """테스트용 쿼리를 여러 번 기록한다."""
        for index in range(1, 6):
            record_query(make_query(index))
        return {"ok": True}

    response = TestClient(app).get("/many-queries")

    assert response.status_code == 200
    event = store.list()[0]
    assert event.query_count == 1
    assert event.total_query_count == 5
    assert event.is_queries_truncated is True


def test_http_exception_object_detail_is_safely_summarized():
    """직접 전파된 HTTPException의 객체 detail 전체를 저장하지 않는다."""
    from tailora.adapters.fastapi.middleware import _summarize_exception

    error = _summarize_exception(
        HTTPException(
            status_code=400,
            detail={"password": "super-secret", "nested": {"token": "value"}},
        ),
    )

    assert error.message == "HTTP Error Details"
    assert "super-secret" not in repr(error)
    assert "nested" not in repr(error)


def test_middleware_rejects_disabled_redaction_policy():
    """저수준 Middleware에서도 Redaction 비활성화 설정을 거부한다."""
    app = FastAPI()

    with pytest.raises(ValueError, match="redaction"):
        TailoraMiddleware(
            app,
            policy=RedactionPolicy(enabled=False),
            enabled=True,
        )


def test_excluded_path_matching_uses_a_path_segment_boundary():
    """제외 prefix와 문자열만 비슷한 다른 경로는 정상적으로 수집한다."""
    app = FastAPI()

    @app.get("/__tailorax/health")
    def similar_path() -> dict[str, str]:
        """Inspector prefix와 비슷하지만 다른 경로의 응답을 반환한다."""
        return {"status": "ok"}

    store = RingBuffer()
    app.add_middleware(TailoraMiddleware, store=store, enabled=True)
    client = TestClient(app)

    assert client.get("/__tailorax/health").status_code == 200
    assert store.size() == 1


def test_broken_query_sequence_normalized_or_handled():
    """쿼리 시퀀스가 어긋나도 API 응답이 성공하고 안전하게 기록되는지 확인한다."""
    store = RingBuffer()
    app = create_test_app(store=store, enabled=True)
    client = TestClient(app)

    response = client.get("/broken-query-sequence")

    assert response.status_code == 200
    assert response.json() == {"status": "broken_query_recorded"}
    assert store.size() == 1

    event = store.list()[0]
    assert event.query_count == 1
    assert event.queries[0].sequence == 1


def test_concurrent_fastapi_requests_captured_independently():
    """동시에 여러 FastAPI 요청이 들어와도 이벤트가 독립적으로 수집되는지 확인한다."""
    store = RingBuffer()
    app = create_test_app(store=store, enabled=True)

    async def run_requests() -> None:
        """비동기 클라이언트로 여러 요청을 동시에 전송한다."""
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            responses = await asyncio.gather(
                client.get("/users/1"),
                client.get("/users/2"),
                client.get("/users/3"),
                client.get("/health"),
            )
            for resp in responses:
                assert resp.status_code == 200

    asyncio.run(run_requests())

    assert store.size() == 4
    events = store.list()
    request_ids = {event.request_id for event in events}
    assert len(request_ids) == 4
