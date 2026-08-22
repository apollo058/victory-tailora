"""SQLAlchemy Engine의 쿼리 실행을 관찰하고 RequestContext에 기록하는 어댑터 모듈."""

from datetime import datetime, timezone
import time
from typing import Any
import uuid

from sqlalchemy import Engine, event

from tailora.core.context import get_current_context, record_query
from tailora.core.events import ErrorSummary, QueryEvent
from tailora.core.privacy import make_sql_fingerprint, redact_sql_statement

_STATE_KEY = "_tailora_query_state"
_REGISTERED_ENGINES: dict[int, dict[str, Any]] = {}


def _extract_database_name(engine: Any, override_name: str | None) -> str:
    """연결 정보에서 비밀번호를 제외한 안전한 데이터베이스 이름을 추출한다."""
    if override_name is not None and override_name.strip():
        return override_name.strip()
    try:
        if hasattr(engine, "dialect") and hasattr(engine.dialect, "name"):
            return str(engine.dialect.name)
    except Exception:
        pass
    return "database"


def _create_query_event(
    sequence: int,
    started_at: datetime,
    duration_ms: float,
    statement: str | None,
    database: str,
    error: ErrorSummary | None = None,
) -> QueryEvent:
    """정규화된 쿼리 정보로 QueryEvent 객체를 만든다."""
    safe_stmt = redact_sql_statement(statement)
    fingerprint = make_sql_fingerprint(statement)
    query_id = str(uuid.uuid4())
    return QueryEvent(
        query_id=query_id,
        sequence=sequence,
        started_at=started_at,
        duration_ms=duration_ms,
        statement=safe_stmt,
        fingerprint=fingerprint,
        database=database,
        error=error,
    )


def _on_before_cursor_execute(
    conn: Any,
    cursor: Any,
    statement: str,
    parameters: Any,
    context: Any,
    executemany: bool,
) -> None:
    """쿼리 실행 직전에 시작 시각과 단조 시계를 context 또는 connection에 보관한다."""
    if get_current_context() is None:
        return
    try:
        state = (
            datetime.now(timezone.utc),
            time.perf_counter(),
            statement,
        )
        if context is not None:
            setattr(context, _STATE_KEY, state)
        elif hasattr(conn, "info"):
            conn.info[_STATE_KEY] = state
    except Exception:
        # 수집기 내부 오류가 SQL 실행을 방해하지 않는다.
        pass


def _on_after_cursor_execute(
    conn: Any,
    cursor: Any,
    statement: str,
    parameters: Any,
    context: Any,
    executemany: bool,
    database_name: str,
) -> None:
    """쿼리 실행 완료 시 실행 시간을 측정하고 QueryEvent를 현재 컨텍스트에 추가한다."""
    try:
        state = None
        if context is not None and hasattr(context, _STATE_KEY):
            state = getattr(context, _STATE_KEY, None)
        elif hasattr(conn, "info"):
            state = conn.info.pop(_STATE_KEY, None)

        if state is None:
            return

        started_at, start_perf, original_stmt = state
        duration_ms = round((time.perf_counter() - start_perf) * 1000.0, 6)

        ctx = get_current_context()
        if ctx is None:
            return

        sequence = len(ctx.queries) + 1
        query_event = _create_query_event(
            sequence=sequence,
            started_at=started_at,
            duration_ms=duration_ms,
            statement=original_stmt,
            database=database_name,
            error=None,
        )
        record_query(query_event)
    except Exception:
        # 수집기 내부 오류가 원래 SQL 결과를 바꾸지 않는다.
        pass


def _on_handle_error(
    exception_context: Any,
    database_name: str,
) -> None:
    """쿼리 실패 시 ErrorSummary가 포함된 QueryEvent를 기록한다."""
    try:
        exec_ctx = getattr(exception_context, "execution_context", None)
        conn = getattr(exception_context, "connection", None)
        state = None
        if exec_ctx is not None and hasattr(exec_ctx, _STATE_KEY):
            state = getattr(exec_ctx, _STATE_KEY, None)
        elif conn and hasattr(conn, "info"):
            state = conn.info.pop(_STATE_KEY, None)

        if state is not None:
            started_at, start_perf, original_stmt = state
            duration_ms = round((time.perf_counter() - start_perf) * 1000.0, 6)
        else:
            started_at = datetime.now(timezone.utc)
            duration_ms = 0.0
            original_stmt = getattr(exception_context, "statement", None)

        ctx = get_current_context()
        if ctx is not None:
            exc = getattr(exception_context, "original_exception", None)
            error_msg = str(exc) if exc else None
            err_type = exc.__class__.__name__ if exc else "DatabaseError"
            error_summary = ErrorSummary(type=err_type, message=error_msg)

            sequence = len(ctx.queries) + 1
            query_event = _create_query_event(
                sequence=sequence,
                started_at=started_at,
                duration_ms=duration_ms,
                statement=original_stmt,
                database=database_name,
                error=error_summary,
            )
            record_query(query_event)
    except Exception:
        # 오류 수집 실패가 원래 DB 예외 전달을 방해하지 않는다.
        pass


def register_sqlalchemy_inspector(
    engine: Engine,
    database_name: str | None = None,
) -> None:
    """SQLAlchemy Engine에 쿼리 수집 이벤트 리스너를 등록한다."""
    if not isinstance(engine, Engine):
        raise TypeError("engine must be a SQLAlchemy Engine instance")

    engine_id = id(engine)
    if engine_id in _REGISTERED_ENGINES:
        return

    db_name = _extract_database_name(engine, database_name)

    def before_exec(conn, cursor, statement, parameters, context, executemany):
        """커서 실행 전 훅."""
        _on_before_cursor_execute(
            conn, cursor, statement, parameters, context, executemany
        )

    def after_exec(conn, cursor, statement, parameters, context, executemany):
        """커서 실행 후 훅."""
        _on_after_cursor_execute(
            conn, cursor, statement, parameters, context, executemany, db_name
        )

    def on_error(exception_context):
        """에러 발생 훅."""
        _on_handle_error(exception_context, db_name)

    event.listen(engine, "before_cursor_execute", before_exec)
    event.listen(engine, "after_cursor_execute", after_exec)
    event.listen(engine, "handle_error", on_error)

    _REGISTERED_ENGINES[engine_id] = {
        "before_cursor_execute": before_exec,
        "after_cursor_execute": after_exec,
        "handle_error": on_error,
    }


def unregister_sqlalchemy_inspector(engine: Engine) -> None:
    """SQLAlchemy Engine에 등록된 쿼리 수집 리스너를 제거한다."""
    engine_id = id(engine)
    listeners = _REGISTERED_ENGINES.pop(engine_id, None)
    if listeners is None:
        return

    for event_name, listener in listeners.items():
        try:
            event.remove(engine, event_name, listener)
        except Exception:
            pass
