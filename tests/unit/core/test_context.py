"""현재 요청 컨텍스트 관리 기능의 동작을 확인한다."""

import asyncio
from datetime import datetime, timezone
import time

import pytest

from tailora.core.context import (
    RequestContext,
    get_current_context,
    record_query,
    reset_current_context,
    set_current_context,
)
from tailora.core.events import QueryEvent

EVENT_TIME = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)


def make_query(sequence: int = 1) -> QueryEvent:
    """테스트용 쿼리 이벤트를 만든다."""
    return QueryEvent(
        query_id=f"q-{sequence}",
        sequence=sequence,
        started_at=EVENT_TIME,
        duration_ms=2.5,
        statement="SELECT 1",
    )


def test_get_current_context_returns_none_by_default():
    """컨텍스트가 설정되지 않았을 때 None을 반환하는지 확인한다."""
    assert get_current_context() is None


def test_set_and_reset_current_context():
    """컨텍스트를 설정하고 다시 원래 상태로 복원할 수 있는지 확인한다."""
    context = RequestContext(
        request_id="req-123",
        started_at=EVENT_TIME,
        start_perf=time.perf_counter(),
    )

    token = set_current_context(context)
    try:
        assert get_current_context() is context
        current = get_current_context()
        assert current is not None
        assert current.request_id == "req-123"
        assert current.queries == []
    finally:
        reset_current_context(token)

    assert get_current_context() is None


def test_record_query_appends_to_current_context():
    """현재 컨텍스트가 있을 때 쿼리가 정상적으로 추가되는지 확인한다."""
    context = RequestContext(
        request_id="req-123",
        started_at=EVENT_TIME,
        start_perf=time.perf_counter(),
    )

    token = set_current_context(context)
    try:
        q1 = make_query(1)
        q2 = make_query(2)
        record_query(q1)
        record_query(q2)

        assert len(context.queries) == 2
        assert context.queries[0] is q1
        assert context.queries[1] is q2
    finally:
        reset_current_context(token)


def test_record_query_applies_limit_while_preserving_totals():
    """쿼리 보관 상한을 즉시 적용하면서 전체 실행 수와 시간을 보존한다."""
    context = RequestContext(
        request_id="req-limited",
        started_at=EVENT_TIME,
        start_perf=time.perf_counter(),
        max_queries_per_request=2,
    )

    token = set_current_context(context)
    try:
        record_query(make_query(1))
        record_query(make_query(2))
        record_query(make_query(3))

        assert len(context.queries) == 2
        assert context.total_query_count == 3
        assert context.total_query_time_ms == pytest.approx(7.5)
    finally:
        reset_current_context(token)


def test_record_query_is_safe_when_no_context():
    """컨텍스트가 없을 때 쿼리 기록이 에러 없이 무시되는지 확인한다."""
    q = make_query(1)
    record_query(q)
    assert get_current_context() is None


def test_nested_context_isolation():
    """중첩 컨텍스트에서 이전 컨텍스트로 올바르게 복구되는지 확인한다."""
    ctx1 = RequestContext(request_id="req-1", started_at=EVENT_TIME, start_perf=1.0)
    ctx2 = RequestContext(request_id="req-2", started_at=EVENT_TIME, start_perf=2.0)

    token1 = set_current_context(ctx1)
    assert get_current_context() is ctx1

    token2 = set_current_context(ctx2)
    assert get_current_context() is ctx2

    reset_current_context(token2)
    assert get_current_context() is ctx1

    reset_current_context(token1)
    assert get_current_context() is None


def test_async_task_context_isolation():
    """비동기 태스크 간에 컨텍스트가 서로 섞이지 않고 격리되는지 확인한다."""

    async def worker(req_id: str, delay: float) -> list[str]:
        """비동기 워커 태스크로 쿼리를 기록하고 결과를 반환한다."""
        ctx = RequestContext(
            request_id=req_id,
            started_at=EVENT_TIME,
            start_perf=time.perf_counter(),
        )
        token = set_current_context(ctx)
        try:
            record_query(make_query(1))
            await asyncio.sleep(delay)
            record_query(make_query(2))

            current = get_current_context()
            assert current is not None
            assert current.request_id == req_id
            return [q.query_id for q in current.queries]
        finally:
            reset_current_context(token)

    async def run_workers():
        """여러 워커를 동시에 실행한다."""
        return await asyncio.gather(
            worker("req-a", 0.02),
            worker("req-b", 0.01),
            worker("req-c", 0.015),
        )

    results = asyncio.run(run_workers())

    assert results == [
        ["q-1", "q-2"],
        ["q-1", "q-2"],
        ["q-1", "q-2"],
    ]
    assert get_current_context() is None
