"""FastAPI와 SQLAlchemy SQLite 통합 쿼리 수집 동작을 확인한다."""

import asyncio
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from tailora.adapters.fastapi import (
    enable_inspector,
    unregister_sqlalchemy_inspector,
)
from tailora.core.store import RingBuffer


def create_sqlite_test_app() -> tuple[FastAPI, Any, RingBuffer]:
    """테스트용 SQLite DB와 연결된 FastAPI 애플리케이션을 생성한다."""
    app = FastAPI(title="SQLite Test App")
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    store = RingBuffer()

    enable_inspector(app, store=store, engine=engine)

    # 테이블 초기화 (요청 밖에서 실행)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE users "
                "(id INTEGER PRIMARY KEY, name TEXT, role TEXT)",
            ),
        )
        conn.execute(
            text("INSERT INTO users VALUES (1, 'alice', 'admin')"),
        )
        conn.execute(
            text("INSERT INTO users VALUES (2, 'bob', 'user')"),
        )

    @app.get("/users/{user_id}")
    def get_user(user_id: int) -> dict[str, str]:
        """사용자 단건 조회 엔드포인트."""
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT name, role FROM users WHERE id = :user_id"),
                {"user_id": user_id},
            ).fetchone()
            if row is None:
                return {"error": "not found"}
            return {"name": row[0], "role": row[1]}

    @app.post("/users")
    def create_user(name: str, role: str) -> dict[str, str]:
        """사용자 생성 및 조회 (2개 쿼리 실행) 엔드포인트."""
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO users (name, role) VALUES (:name, :role)"),
                {"name": name, "role": role},
            )
            count = conn.execute(text("SELECT count(*) FROM users")).scalar()
        return {"name": name, "total_users": str(count)}

    @app.get("/db-error")
    def db_error_route() -> None:
        """잘못된 컬럼을 조회하여 DB 예외를 일으키는 엔드포인트."""
        with engine.connect() as conn:
            conn.execute(text("SELECT invalid_column FROM users"))

    return app, engine, store


def test_sqlite_queries_captured_in_request_event():
    """FastAPI 요청에서 실행된 SQLite 쿼리가 RequestEvent에 기록되는지 확인한다."""
    app, engine, store = create_sqlite_test_app()
    try:
        client = TestClient(app)
        response = client.get("/users/1")

        assert response.status_code == 200
        assert response.json() == {"name": "alice", "role": "admin"}
        assert store.size() == 1

        event = store.list()[0]
        assert event.query_count == 1
        assert event.query_time_ms >= 0
        assert len(event.queries) == 1

        query = event.queries[0]
        assert query.sequence == 1
        assert query.database == "sqlite"
        assert query.statement == "SELECT name, role FROM users WHERE id = ?"
        assert query.fingerprint == "select name, role from users where id = ?"
        assert query.error is None
    finally:
        unregister_sqlalchemy_inspector(engine)
        engine.dispose()


def test_multiple_queries_sequence_and_aggregation():
    """한 요청에서 실행된 복수 쿼리의 순서와 총 쿼리 시간이 정확히 집계되는지 확인한다."""
    app, engine, store = create_sqlite_test_app()
    try:
        client = TestClient(app)
        response = client.post("/users?name=charlie&role=guest")

        assert response.status_code == 200
        assert store.size() == 1

        event = store.list()[0]
        assert event.query_count == 2
        assert event.queries[0].sequence == 1
        assert event.queries[1].sequence == 2
        assert "insert into users" in (event.queries[0].fingerprint or "")
        assert "select count(*)" in (event.queries[1].fingerprint or "")
        assert event.query_time_ms == round(
            sum(q.duration_ms for q in event.queries), 6
        )
    finally:
        unregister_sqlalchemy_inspector(engine)
        engine.dispose()


def test_database_error_creates_failed_query_and_500_response():
    """DB 오류 발생 시 500 응답과 함께 실패한 QueryEvent가 기록되는지 확인한다."""
    app, engine, store = create_sqlite_test_app()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/db-error")

        assert response.status_code == 500
        assert store.size() == 1

        event = store.list()[0]
        assert event.status_code == 500
        assert event.query_count == 1

        failed_query = event.queries[0]
        assert failed_query.error is not None
        assert "no such column" in (failed_query.error.message or "").lower()
    finally:
        unregister_sqlalchemy_inspector(engine)
        engine.dispose()


def test_concurrent_requests_isolate_sqlite_queries():
    """동시 요청 시 각 요청별 SQLite 쿼리가 올바르게 격리되는지 확인한다."""
    app, engine, store = create_sqlite_test_app()
    try:

        async def run_concurrent():
            """비동기 클라이언트로 동시에 여러 요청을 보낸다."""
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                resps = await asyncio.gather(
                    client.get("/users/1"),
                    client.get("/users/2"),
                    client.get("/users/1"),
                )
                for r in resps:
                    assert r.status_code == 200

        asyncio.run(run_concurrent())

        assert store.size() == 3
        events = store.list()
        for ev in events:
            assert ev.query_count == 1
            assert len(ev.queries) == 1
    finally:
        unregister_sqlalchemy_inspector(engine)
        engine.dispose()
