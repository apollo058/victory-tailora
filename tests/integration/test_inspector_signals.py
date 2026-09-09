"""FastAPI Inspector API의 신호(Signals) 반환 동작을 확인한다."""

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tailora.adapters.fastapi import enable_inspector
from tailora.core.events import QueryEvent, RequestEvent
from tailora.core.policies import ThresholdPolicy
from tailora.core.store import RingBuffer

EVENT_TIME = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)


def make_query(
    sequence: int = 1,
    duration_ms: float = 10.0,
    statement: str = "SELECT 1",
    fingerprint: str | None = None,
) -> QueryEvent:
    """테스트용 쿼리 이벤트를 생성한다."""
    fp = fingerprint if fingerprint is not None else statement.lower()
    return QueryEvent(
        query_id=f"q-{sequence}",
        sequence=sequence,
        started_at=EVENT_TIME,
        duration_ms=duration_ms,
        statement=statement,
        fingerprint=fp,
        database="sqlite",
    )


def make_request(
    request_id: str,
    duration_ms: float = 100.0,
    queries: list[QueryEvent] | None = None,
) -> RequestEvent:
    """테스트용 요청 이벤트를 생성한다."""
    return RequestEvent(
        request_id=request_id,
        timestamp=EVENT_TIME,
        framework="fastapi",
        method="GET",
        route_template="/items",
        status_code=200,
        duration_ms=duration_ms,
        queries=queries or [],
    )


def create_signals_app(
    store: RingBuffer | None = None,
    threshold_policy: ThresholdPolicy | None = None,
) -> tuple[FastAPI, RingBuffer]:
    """신호 검증용 FastAPI 앱을 생성한다."""
    app = FastAPI(title="Signals Test App")
    resolved_store = enable_inspector(
        app,
        store=store,
        threshold_policy=threshold_policy,
        enabled=True,
    )
    return app, resolved_store


def test_requests_list_includes_signals_summary():
    """요청 목록 응답의 각 항목에 경량 신호 요약이 포함되는지 확인한다."""
    store = RingBuffer()
    # 600ms (slow_request), 쿼리 2개 동일 fp (duplicate_query)
    q1 = make_query(1, 10.0, statement="SELECT * FROM users WHERE id = ?")
    q2 = make_query(2, 10.0, statement="SELECT * FROM users WHERE id = ?")
    req = make_request("req-1", duration_ms=600.0, queries=[q1, q2])
    store.add(req)

    app, _ = create_signals_app(store=store)
    client = TestClient(app)

    response = client.get("/__tailora/requests")
    assert response.status_code == 200
    data = response.json()

    assert data["count"] == 1
    item = data["items"][0]
    assert "signals" in item
    assert item["signals"]["slow_request"] is True
    assert item["signals"]["has_slow_query"] is False
    assert item["signals"]["has_duplicate_query"] is True
    assert item["signals"]["query_heavy"] is False


def test_request_detail_includes_signals_detail():
    """요청 상세 응답에 상세 신호 분석 결과가 포함되는지 확인한다."""
    store = RingBuffer()
    # 150ms 쿼리 (slow_query >= 100ms), 2개 동일 fp (duplicate)
    q1 = make_query(1, 150.0, statement="SELECT * FROM items WHERE id = ?")
    q2 = make_query(2, 20.0, statement="SELECT * FROM items WHERE id = ?")
    req = make_request("req-detail", duration_ms=200.0, queries=[q1, q2])
    store.add(req)

    app, _ = create_signals_app(store=store)
    client = TestClient(app)

    response = client.get("/__tailora/requests/req-detail")
    assert response.status_code == 200
    data = response.json()

    assert "signals" in data
    signals = data["signals"]
    assert signals["slow_request"] is False
    assert signals["slow_queries"] == [1]
    assert len(signals["duplicate_queries"]) == 1
    assert signals["duplicate_queries"][0]["fingerprint"] == (
        "select * from items where id = ?"
    )
    assert signals["duplicate_queries"][0]["sequences"] == [1, 2]
    assert signals["query_heavy"] is False


def test_aggregates_includes_threshold_metadata():
    """집계 엔드포인트 응답에 임계값 메타데이터가 포함되는지 확인한다."""
    app, _ = create_signals_app()
    client = TestClient(app)

    response = client.get("/__tailora/aggregates")
    assert response.status_code == 200
    data = response.json()

    assert "thresholds" in data
    thresholds = data["thresholds"]
    assert thresholds["slow_request_ms"] == 500.0
    assert thresholds["slow_query_ms"] == 100.0
    assert thresholds["duplicate_query_threshold"] == 2
    assert thresholds["query_heavy_count"] == 10
    assert thresholds["query_heavy_time_ms"] == 200.0


def test_custom_threshold_policy_applied_to_api():
    """커스텀 임계값 설정이 API 판정에 올바르게 적용되는지 확인한다."""
    custom_policy = ThresholdPolicy(
        slow_request_ms=50.0,
        slow_query_ms=20.0,
    )
    store = RingBuffer()
    # 60ms는 기본(500)에선 빠르지만 커스텀(50)에선 slow
    req = make_request("req-custom", duration_ms=60.0)
    store.add(req)

    app, _ = create_signals_app(
        store=store,
        threshold_policy=custom_policy,
    )
    client = TestClient(app)

    response = client.get("/__tailora/requests")
    assert response.status_code == 200
    data = response.json()

    assert data["items"][0]["signals"]["slow_request"] is True
