"""Inspector 개발을 위한 최소 FastAPI 애플리케이션."""

from fastapi import FastAPI

from tailora.adapters.fastapi import enable_inspector
from tailora.core.store import RingBuffer

app = FastAPI(title="Tailora FastAPI Example")
store = RingBuffer()

enable_inspector(app, store=store)


@app.get("/health")
def health_check() -> dict[str, str]:
    """애플리케이션의 현재 상태를 반환한다."""
    return {"status": "ok"}
