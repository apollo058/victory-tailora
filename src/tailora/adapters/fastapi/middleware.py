"""FastAPI 애플리케이션의 요청과 쿼리를 측정하는 ASGI 미들웨어."""

import dataclasses
from datetime import datetime, timezone
import json
import time
from typing import Any, Callable, Coroutine
import uuid

from fastapi import HTTPException

from tailora.core.context import (
    RequestContext,
    reset_current_context,
    set_current_context,
)
from tailora.core.enums import Framework
from tailora.core.events import ErrorSummary, QueryEvent, RequestEvent
from tailora.core.policies import RedactionPolicy
from tailora.core.privacy import redact_event
from tailora.core.store import RingBuffer

Scope = dict[str, Any]
Receive = Callable[[], Coroutine[Any, Any, dict[str, Any]]]
Send = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]
ASGIApp = Callable[[Scope, Receive, Send], Coroutine[Any, Any, None]]

DEFAULT_EXCLUDED_PATHS: tuple[str, ...] = ("/__tailora",)


def _is_excluded_path(path: str, prefixes: tuple[str, ...]) -> bool:
    """요청 경로가 수집 제외 대상 경로로 시작하는지 확인한다."""
    return any(path.startswith(prefix) for prefix in prefixes)


def _extract_route_template(scope: Scope, fallback_path: str) -> str:
    """FastAPI 라우팅 정보에서 경로 패턴(예: /users/{id})을 추출한다."""
    route = scope.get("route")
    if route is not None:
        if hasattr(route, "path_format") and isinstance(route.path_format, str):
            return route.path_format
        if hasattr(route, "path") and isinstance(route.path, str):
            return route.path
    return fallback_path or "/"


def _summarize_exception(exc: Exception) -> ErrorSummary:
    """발생한 예외 객체에서 안전한 ErrorSummary를 만든다."""
    if isinstance(exc, HTTPException):
        detail = str(exc.detail) if exc.detail is not None else None
        return ErrorSummary(type=exc.__class__.__name__, message=detail)
    message = str(exc) if str(exc) else None
    return ErrorSummary(type=exc.__class__.__name__, message=message)


def _extract_error_from_body(body_bytes: bytes, status_code: int) -> ErrorSummary | None:
    """에러 응답 본문에서 메시지를 추출해 ErrorSummary를 만든다."""
    if not body_bytes or status_code < 400:
        return None
    try:
        data = json.loads(body_bytes.decode("utf-8", errors="ignore"))
        if isinstance(data, dict) and "detail" in data:
            detail = data["detail"]
            msg = detail if isinstance(detail, str) else json.dumps(detail)
            err_type = "HTTPException" if status_code < 500 else "HTTPError"
            return ErrorSummary(type=err_type, message=msg)
    except Exception:
        pass
    default_type = "HTTPException" if status_code < 500 else "HTTPError"
    return ErrorSummary(type=default_type, message=f"HTTP {status_code}")


def _safe_normalize_queries(queries: list[QueryEvent]) -> list[QueryEvent]:
    """쿼리 시퀀스가 끊기지 않도록 순서대로 번호를 보정한다."""
    normalized: list[QueryEvent] = []
    for expected_seq, query in enumerate(queries, start=1):
        if not isinstance(query, QueryEvent):
            continue
        if query.sequence != expected_seq:
            normalized.append(dataclasses.replace(query, sequence=expected_seq))
        else:
            normalized.append(query)
    return normalized


def _create_request_event(
    request_id: str,
    started_at: datetime,
    duration_ms: float,
    method: str,
    route_template: str,
    status_code: int,
    queries: list[QueryEvent],
    error: ErrorSummary | None,
) -> RequestEvent:
    """수집된 측정 정보로 RequestEvent 객체를 완성한다."""
    safe_queries = _safe_normalize_queries(queries)
    return RequestEvent(
        request_id=request_id,
        timestamp=started_at,
        framework=Framework.FASTAPI,
        method=method,
        route_template=route_template,
        status_code=status_code,
        duration_ms=duration_ms,
        queries=safe_queries,
        error=error,
    )


def _safe_store_event(
    store: RingBuffer,
    event: RequestEvent,
    policy: RedactionPolicy,
) -> None:
    """민감정보를 마스킹한 뒤 링버퍼에 안전하게 저장한다."""
    try:
        redacted = redact_event(event, policy)
        store.add(redacted)
    except Exception:
        # 수집기 내부의 오류가 API 응답을 깨뜨려서는 안 된다.
        pass


class TailoraMiddleware:
    """FastAPI 요청의 실행 시간, 쿼리, 상태 코드를 링버퍼에 기록하는 미들웨어."""

    def __init__(
        self,
        app: ASGIApp,
        store: RingBuffer | None = None,
        policy: RedactionPolicy | None = None,
        enabled: bool = False,
        excluded_paths: tuple[str, ...] = DEFAULT_EXCLUDED_PATHS,
    ) -> None:
        """미들웨어의 저장소, 마스킹 정책, 활성화 여부를 설정한다."""
        self.app = app
        self.store = store if store is not None else RingBuffer()
        self.policy = policy if policy is not None else RedactionPolicy()
        self.enabled = enabled
        self.excluded_paths = excluded_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """HTTP 요청을 측정하고 완료 시 RequestEvent로 저장한다."""
        if scope.get("type") != "http" or not self.enabled:
            await self.app(scope, receive, send)
            return

        raw_path = scope.get("root_path", "") + scope.get("path", "")
        if _is_excluded_path(raw_path, self.excluded_paths):
            await self.app(scope, receive, send)
            return

        await self._capture_request(scope, receive, send, raw_path)

    async def _capture_request(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        raw_path: str,
    ) -> None:
        """단일 HTTP 요청의 컨텍스트를 생성하고 완료 후 이벤트를 저장한다."""
        request_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)
        start_perf = time.perf_counter()
        method = str(scope.get("method", "GET")).upper()

        context = RequestContext(
            request_id=request_id,
            started_at=started_at,
            start_perf=start_perf,
        )
        token = set_current_context(context)
        status_code: int = 500
        error_summary: ErrorSummary | None = None

        async def wrapped_send(message: dict[str, Any]) -> None:
            """응답 상태 코드와 에러 메시지를 가로채고 원래 send를 호출한다."""
            nonlocal status_code, error_summary
            msg_type = message.get("type")
            if msg_type == "http.response.start":
                status_code = int(message.get("status", 200))
            elif msg_type == "http.response.body" and status_code >= 400:
                if error_summary is None:
                    body_chunk = message.get("body", b"")
                    error_summary = _extract_error_from_body(body_chunk, status_code)
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        except HTTPException as exc:
            status_code = exc.status_code
            error_summary = _summarize_exception(exc)
            raise
        except Exception as exc:
            status_code = 500
            error_summary = _summarize_exception(exc)
            raise
        finally:
            self._finalize_request(
                scope=scope,
                raw_path=raw_path,
                request_id=request_id,
                started_at=started_at,
                start_perf=start_perf,
                method=method,
                status_code=status_code,
                context=context,
                error_summary=error_summary,
                token=token,
            )

    def _finalize_request(
        self,
        scope: Scope,
        raw_path: str,
        request_id: str,
        started_at: datetime,
        start_perf: float,
        method: str,
        status_code: int,
        context: RequestContext,
        error_summary: ErrorSummary | None,
        token: Any,
    ) -> None:
        """요청 측정을 종료하고 이벤트를 완성하여 저장한 뒤 컨텍스트를 복원한다."""
        try:
            duration_ms = round((time.perf_counter() - start_perf) * 1000.0, 6)
            route_template = _extract_route_template(scope, raw_path)
            event = _create_request_event(
                request_id=request_id,
                started_at=started_at,
                duration_ms=duration_ms,
                method=method,
                route_template=route_template,
                status_code=status_code,
                queries=context.queries,
                error=error_summary,
            )
            _safe_store_event(self.store, event, self.policy)
        except Exception:
            # 이벤트 생성 및 저장 실패 등 모든 수집기 내부 오류를 흡수한다.
            pass
        finally:
            reset_current_context(token)
