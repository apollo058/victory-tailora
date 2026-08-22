"""Inspector 개발을 위한 최소 FastAPI 애플리케이션."""

from fastapi import FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from tailora.adapters.fastapi import enable_inspector
from tailora.core.store import RingBuffer

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

enable_inspector(app, store=store, engine=engine)


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
