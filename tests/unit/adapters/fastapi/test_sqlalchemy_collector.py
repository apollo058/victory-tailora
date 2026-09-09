"""SQLAlchemy 쿼리 수집기의 단위 동작을 확인한다."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import time
from threading import Lock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.pool import StaticPool

from tailora.adapters.fastapi.sqlalchemy import (
    register_sqlalchemy_inspector,
    unregister_sqlalchemy_inspector,
)
import tailora.adapters.fastapi.sqlalchemy as sqlalchemy_adapter
from tailora.core.context import (
    RequestContext,
    get_current_context,
    reset_current_context,
    set_current_context,
)

EVENT_TIME = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def engine():
    """테스트용 SQLite 인메모리 엔진을 생성하고 종료 시 정리한다."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    yield test_engine
    unregister_sqlalchemy_inspector(test_engine)
    test_engine.dispose()


def test_register_and_unregister_inspector(engine):
    """엔진에 인스펙터를 등록하고 해제할 수 있는지 확인한다."""
    register_sqlalchemy_inspector(engine)

    ctx = RequestContext(
        request_id="req-1",
        started_at=EVENT_TIME,
        start_perf=time.perf_counter(),
    )
    token = set_current_context(ctx)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        assert len(ctx.queries) == 1

        unregister_sqlalchemy_inspector(engine)
        with engine.connect() as conn:
            conn.execute(text("SELECT 2"))
        assert len(ctx.queries) == 1
    finally:
        reset_current_context(token)


def test_duplicate_registration_prevented(engine):
    """동일한 엔진에 중복 등록해도 리스너가 한 번만 실행되는지 확인한다."""
    register_sqlalchemy_inspector(engine)
    register_sqlalchemy_inspector(engine)

    ctx = RequestContext(
        request_id="req-dup",
        started_at=EVENT_TIME,
        start_perf=time.perf_counter(),
    )
    token = set_current_context(ctx)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        assert len(ctx.queries) == 1
    finally:
        reset_current_context(token)


def test_concurrent_engine_registration_is_idempotent(engine, monkeypatch):
    """동시에 같은 엔진을 등록해도 listener가 한 번만 추가되는지 확인한다."""
    original_listen = sqlalchemy_adapter.event.listen
    call_count = 0
    count_lock = Lock()

    def delayed_listen(target, event_name, listener):
        """listener 등록 사이에 지연을 넣어 동시 호출을 재현한다."""
        nonlocal call_count
        with count_lock:
            call_count += 1
        time.sleep(0.01)
        return original_listen(target, event_name, listener)

    monkeypatch.setattr(sqlalchemy_adapter.event, "listen", delayed_listen)

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(
                sqlalchemy_adapter.register_sqlalchemy_inspector,
                engine,
            )
            for _ in range(8)
        ]
        for future in futures:
            future.result()

    assert call_count == 3


def test_partial_listener_registration_is_rolled_back(engine, monkeypatch):
    """SQLAlchemy listener 등록 중 실패하면 이미 추가한 listener를 제거한다."""
    original_listen = sqlalchemy_adapter.event.listen
    original_remove = sqlalchemy_adapter.event.remove
    listen_count = 0
    removed_events: list[str] = []

    def fail_second_listener(target, event_name, listener):
        """두 번째 listener 등록에서 실패를 재현한다."""
        nonlocal listen_count
        listen_count += 1
        if listen_count == 2:
            raise RuntimeError("listener registration failed")
        original_listen(target, event_name, listener)

    def record_listener_removal(target, event_name, listener):
        """롤백으로 제거된 listener 종류를 기록한다."""
        removed_events.append(event_name)
        original_remove(target, event_name, listener)

    monkeypatch.setattr(sqlalchemy_adapter.event, "listen", fail_second_listener)
    monkeypatch.setattr(sqlalchemy_adapter.event, "remove", record_listener_removal)

    with pytest.raises(RuntimeError, match="listener registration failed"):
        register_sqlalchemy_inspector(engine)

    assert removed_events == ["before_cursor_execute"]


def test_query_ignored_when_no_active_context(engine):
    """활성 컨텍스트가 없을 때 쿼리가 기록되지 않는지 확인한다."""
    register_sqlalchemy_inspector(engine)

    assert get_current_context() is None
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        assert result.scalar() == 1
    assert get_current_context() is None


def test_multiple_queries_sequence_increment(engine):
    """한 요청 안에서 여러 쿼리의 sequence 번호가 순차 증가하는지 확인한다."""
    register_sqlalchemy_inspector(engine)

    ctx = RequestContext(
        request_id="req-multi",
        started_at=EVENT_TIME,
        start_perf=time.perf_counter(),
    )
    token = set_current_context(ctx)
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE items (id INTEGER, name TEXT)"))
            conn.execute(text("INSERT INTO items VALUES (1, 'apple')"))
            conn.execute(text("SELECT * FROM items"))

        assert len(ctx.queries) == 3
        assert ctx.queries[0].sequence == 1
        assert ctx.queries[1].sequence == 2
        assert ctx.queries[2].sequence == 3
        assert ctx.queries[0].duration_ms >= 0
        assert ctx.queries[1].duration_ms >= 0
        assert ctx.queries[2].duration_ms >= 0
    finally:
        reset_current_context(token)


def test_database_error_captured_and_reraised(engine):
    """SQL 실패 시 에러 요약이 저장되고 원래 예외가 다시 발생하는지 확인한다."""
    register_sqlalchemy_inspector(engine)

    ctx = RequestContext(
        request_id="req-err",
        started_at=EVENT_TIME,
        start_perf=time.perf_counter(),
    )
    token = set_current_context(ctx)
    try:
        with pytest.raises((OperationalError, DBAPIError)):
            with engine.connect() as conn:
                conn.execute(text("SELECT * FROM nonexistent_table"))

        assert len(ctx.queries) == 1
        query = ctx.queries[0]
        assert query.error is not None
        assert "no such table" in (query.error.message or "").lower()
    finally:
        reset_current_context(token)


def test_sql_parameters_and_literals_redacted(engine):
    """SQL의 값 리터럴이 마스킹되고 fingerprint가 생성되는지 확인한다."""
    register_sqlalchemy_inspector(engine)

    ctx = RequestContext(
        request_id="req-secret",
        started_at=EVENT_TIME,
        start_perf=time.perf_counter(),
    )
    token = set_current_context(ctx)
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE users (id INT, password TEXT)"))
            conn.execute(
                text("SELECT * FROM users WHERE password = 'my_super_secret_pw'"),
            )

        assert len(ctx.queries) == 2
        select_query = ctx.queries[1]
        assert "my_super_secret_pw" not in (select_query.statement or "")
        assert select_query.statement == "SELECT * FROM users WHERE password = ?"
        assert select_query.fingerprint == "select * from users where password = ?"
    finally:
        reset_current_context(token)
