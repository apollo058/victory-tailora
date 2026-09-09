"""FastAPI 애플리케이션의 요청과 쿼리를 측정하는 ASGI 미들웨어."""

import dataclasses
from datetime import datetime, timezone
import json
import logging
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
from tailora.core.privacy import redact_error_summary, redact_event
from tailora.core.store import RingBuffer

Scope = dict[str, Any]
Receive = Callable[[], Coroutine[Any, Any, dict[str, Any]]]
Send = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]
ASGIApp = Callable[[Scope, Receive, Send], Coroutine[Any, Any, None]]

DEFAULT_EXCLUDED_PATHS: tuple[str, ...] = ("/__tailora",)

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class _CaptureState:
    """한 HTTP 요청을 측정하는 동안 변하는 상태를 보관한다."""

    request_id: str
    started_at: datetime
    start_perf: float
    method: str
    context: RequestContext
    token: Any
    status_code: int = 500
    error_summary: ErrorSummary | None = None


def _is_excluded_path(path: str, prefixes: tuple[str, ...]) -> bool:
    """요청 경로가 수집 제외 대상 경로로 시작하는지 확인한다."""
    for prefix in prefixes:
        normalized = prefix.rstrip("/") or "/"
        if normalized == "/" or path == normalized:
            return True
        if path.startswith(f"{normalized}/"):
            return True
    return False


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
        detail = (
            _extract_detail_message(exc.detail)
            if exc.detail is not None
            else None
        )
        return ErrorSummary(type=exc.__class__.__name__, message=detail)
    message = str(exc) if str(exc) else None
    return ErrorSummary(type=exc.__class__.__name__, message=message)


def _extract_detail_message(detail: Any) -> str:
    """에러 detail 객체에서 안전한 요약 문자열만 추출한다."""
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        for key in ("msg", "message", "detail", "error"):
            val = detail.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return "HTTP Error Details"
    if isinstance(detail, list) and detail:
        first = detail[0]
        if isinstance(first, dict):
            for key in ("msg", "message"):
                val = first.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
        return "Validation Error"
    return "HTTP Error"


def _extract_error_from_body(
    body_bytes: bytes,
    status_code: int,
    policy: RedactionPolicy | None = None,
) -> ErrorSummary | None:
    """에러 응답 본문에서 요약 메시지를 추출하고 민감정보를 마스킹한다."""
    if not body_bytes or status_code < 400:
        return None
    raw_message = f"HTTP {status_code}"
    try:
        data = json.loads(body_bytes.decode("utf-8", errors="ignore"))
        if isinstance(data, dict) and "detail" in data:
            raw_message = _extract_detail_message(data["detail"])
    except Exception:
        pass

    err_type = "HTTPException" if status_code < 500 else "HTTPError"
    raw_summary = ErrorSummary(type=err_type, message=raw_message)
    return redact_error_summary(raw_summary, policy)


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
    total_query_count: int | None = None,
    total_query_time_ms: float | None = None,
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
        total_query_count=total_query_count,
        total_query_time_ms=total_query_time_ms,
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
        logger.warning("Tailora event collection failed")


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
        if not isinstance(self.policy, RedactionPolicy):
            raise ValueError("policy must be a RedactionPolicy")
        self.enabled = enabled
        if self.enabled and not self.policy.enabled:
            raise ValueError("redaction policy must remain enabled")
        self.excluded_paths = excluded_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """HTTP 요청을 측정하고 완료 시 RequestEvent로 저장한다."""
        if scope.get("type") != "http" or not self.enabled:
            await self.app(scope, receive, send)
            return

        request_path = str(scope.get("path", ""))
        raw_path = str(scope.get("root_path", "")) + request_path
        if _is_excluded_path(
            raw_path,
            self.excluded_paths,
        ) or _is_excluded_path(request_path, self.excluded_paths):
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
        state = self._start_capture(scope)
        wrapped_send = self._wrap_send(send, state)
        try:
            await self.app(scope, receive, wrapped_send)
        except HTTPException as error:
            state.status_code = error.status_code
            state.error_summary = _summarize_exception(error)
            raise
        except Exception as error:
            state.status_code = 500
            state.error_summary = _summarize_exception(error)
            raise
        finally:
            self._finalize_request(scope, raw_path, state)

    def _start_capture(self, scope: Scope) -> _CaptureState:
        """요청 ID, 시각, 쿼리 컨텍스트를 생성해 측정을 시작한다."""
        request_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)
        start_perf = time.perf_counter()
        method = str(scope.get("method", "GET")).upper()
        context = RequestContext(
            request_id=request_id,
            started_at=started_at,
            start_perf=start_perf,
            max_queries_per_request=self.policy.max_queries_per_request,
        )
        token = set_current_context(context)
        return _CaptureState(
            request_id=request_id,
            started_at=started_at,
            start_perf=start_perf,
            method=method,
            context=context,
            token=token,
        )

    def _wrap_send(self, send: Send, state: _CaptureState) -> Send:
        """응답 상태와 안전한 오류 요약만 측정하는 send wrapper를 만든다."""
        async def wrapped_send(message: dict[str, Any]) -> None:
            """응답 상태 코드와 에러 메시지를 가로채고 원래 send를 호출한다."""
            msg_type = message.get("type")
            if msg_type == "http.response.start":
                state.status_code = int(message.get("status", 200))
            elif msg_type == "http.response.body" and state.status_code >= 400:
                if state.error_summary is None:
                    body_chunk = message.get("body", b"")
                    state.error_summary = _extract_error_from_body(
                        body_chunk,
                        state.status_code,
                        self.policy,
                    )
            await send(message)
        return wrapped_send

    def _finalize_request(
        self,
        scope: Scope,
        raw_path: str,
        state: _CaptureState,
    ) -> None:
        """요청 측정을 종료하고 이벤트를 완성하여 저장한 뒤 컨텍스트를 복원한다."""
        try:
            duration_ms = round(
                (time.perf_counter() - state.start_perf) * 1000.0,
                6,
            )
            route_template = _extract_route_template(scope, raw_path)
            event = _create_request_event(
                request_id=state.request_id,
                started_at=state.started_at,
                duration_ms=duration_ms,
                method=state.method,
                route_template=route_template,
                status_code=state.status_code,
                queries=state.context.queries,
                error=state.error_summary,
                total_query_count=state.context.total_query_count,
                total_query_time_ms=state.context.total_query_time_ms,
            )
            _safe_store_event(self.store, event, self.policy)
        except Exception:
            logger.warning("Tailora event finalization failed")
        finally:
            reset_current_context(state.token)
