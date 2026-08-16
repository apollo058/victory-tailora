"""Inspector 개발을 위한 최소 FastAPI 애플리케이션."""

from fastapi import FastAPI

app = FastAPI(title="Tailora FastAPI Example")


@app.get("/health")
def health_check() -> dict[str, str]:
    """애플리케이션의 현재 상태를 반환한다."""
    return {"status": "ok"}
