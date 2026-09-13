"""설치 직후 Inspector 진단 흐름을 재현하는 FastAPI 예제 애플리케이션."""

import time

from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from tailora.adapters.fastapi import enable_inspector
from tailora.core.store import RingBuffer
from tailora.core.policies import ThresholdPolicy

SLOW_REQUEST_SECONDS = 0.04
SLOW_QUERY_SECONDS = 0.03

app = FastAPI(title="Tailora FastAPI Example")
store = RingBuffer()
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

with engine.begin() as conn:
    conn.execute(
        text("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)"),
    )
    conn.execute(
        text("INSERT INTO users VALUES (1, 'Alice'), (2, 'Bob')"),
    )


def _sqlite_sleep(seconds: float) -> int:
    """SQLite 쿼리 안에서 짧고 결정적인 지연을 발생시킨다."""
    time.sleep(min(max(float(seconds), 0.0), 0.2))
    return 0


def _install_sqlite_demo_function() -> None:
    """인메모리 SQLite 연결에 느린 쿼리 재현용 함수를 등록한다."""
    raw_connection = engine.raw_connection()
    try:
        raw_connection.create_function("tailora_sleep", 1, _sqlite_sleep)
    finally:
        raw_connection.close()


_install_sqlite_demo_function()

enable_inspector(
    app,
    store=store,
    engine=engine,
    threshold_policy=ThresholdPolicy(
        slow_request_ms=25.0,
        slow_query_ms=15.0,
        duplicate_query_threshold=2,
        query_heavy_count=3,
        query_heavy_time_ms=40.0,
    ),
    enabled=True,
)


@app.get("/health")
def health_check() -> dict[str, str]:
    """애플리케이션의 현재 상태를 반환한다."""
    return {"status": "ok"}


@app.get("/users/{user_id}")
def get_user(user_id: int) -> dict[str, str]:
    """사용자 조회 및 DB 쿼리 실행 예제 엔드포인트."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT name FROM users WHERE id = :user_id"),
            {"user_id": user_id},
        ).fetchone()
        if row is None:
            return {"error": "not found"}
        return {"id": str(user_id), "name": row[0]}


def _read_user(user_id: int) -> dict[str, str]:
    """SQLite에서 사용자 한 명을 읽어 응답 사전으로 변환한다."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT name FROM users WHERE id = :user_id"),
            {"user_id": user_id},
        ).fetchone()
    if row is None:
        return {"error": "not found"}
    return {"id": str(user_id), "name": row[0]}


@app.get("/users/repeat/{user_id}")
def repeat_user(user_id: int) -> dict[str, list[dict[str, str]]]:
    """같은 사용자를 두 번 조회해 duplicate query 신호를 재현한다."""
    return {"items": [_read_user(user_id), _read_user(user_id)]}


@app.get("/slow")
def slow_request() -> dict[str, str]:
    """설정된 요청 threshold를 넘는 처리 지연을 재현한다."""
    time.sleep(SLOW_REQUEST_SECONDS)
    return {"status": "slow"}


@app.get("/slow-query")
def slow_query() -> dict[str, int]:
    """SQLite 사용자 정의 함수로 설정된 SQL threshold를 넘긴다."""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT tailora_sleep(:seconds) AS slept"),
            {"seconds": SLOW_QUERY_SECONDS},
        ).scalar_one()
    return {"slept": int(result)}


@app.get("/secret-query")
def secret_query() -> dict[str, str]:
    """SQL literal을 반환하지 않고 Inspector redaction만 재현한다."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 'sql-demo-secret' AS value")).scalar_one()
    return {"status": "redacted"}


@app.get("/secret-error")
def secret_error(token: str | None = None) -> None:
    """토큰 입력을 받아도 오류 응답에는 안전한 요약만 반환한다."""
    del token
    raise HTTPException(
        status_code=400,
        detail={"message": "Invalid token provided"},
    )


@app.get("/db-error")
def database_error() -> None:
    """잘못된 컬럼을 조회해 실패한 SQL 이벤트를 재현한다."""
    with engine.connect() as conn:
        conn.execute(text("SELECT invalid_column FROM users"))
