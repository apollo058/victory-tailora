"""FastAPI Inspector 요청의 접근 조건을 안전하게 검사한다."""

from collections.abc import Sequence
import inspect
import logging
from typing import Any

from fastapi import HTTPException, Request, params

from tailora.config import AccessCheck

AUTHENTICATION_REQUIRED_MESSAGE = "Inspector authentication required."
ACCESS_DENIED_MESSAGE = "Inspector access denied."

logger = logging.getLogger(__name__)


def normalize_inspector_dependencies(
    dependencies: Sequence[params.Depends] | None,
) -> tuple[params.Depends, ...]:
    """Inspector 인증 dependency 목록의 자료형과 항목을 검증한다."""
    if dependencies is None:
        return ()
    if isinstance(dependencies, (str, bytes)) or not isinstance(
        dependencies,
        Sequence,
    ):
        raise ValueError("dependencies must be a sequence of Depends values")
    resolved = tuple(dependencies)
    if any(
        not isinstance(dependency, params.Depends)
        or not callable(dependency.dependency)
        for dependency in resolved
    ):
        raise ValueError("dependencies must contain only callable Depends values")
    return resolved


def _safe_access_error(status_code: int = 403) -> HTTPException:
    """민감한 상세 정보가 없는 Inspector 접근 오류를 만든다."""
    if status_code == 401:
        return HTTPException(
            status_code=401,
            detail=AUTHENTICATION_REQUIRED_MESSAGE,
        )
    return HTTPException(status_code=403, detail=ACCESS_DENIED_MESSAGE)


async def _resolve_access_result(
    request: Any,
    access_check: AccessCheck,
) -> object:
    """동기 또는 비동기 접근 hook의 결과를 하나의 값으로 만든다."""
    result = access_check(request)
    if inspect.isawaitable(result):
        return await result
    return result


async def enforce_inspector_access(
    request: Any,
    access_check: AccessCheck | None,
) -> None:
    """Inspector 접근 hook을 실행하고 허용된 요청만 통과시킨다."""
    if access_check is None:
        return
    try:
        result = await _resolve_access_result(request, access_check)
    except HTTPException as error:
        logger.warning("Tailora Inspector access check rejected a request")
        safe_status = error.status_code if error.status_code in {401, 403} else 403
        raise _safe_access_error(safe_status) from None
    except Exception:
        logger.warning("Tailora Inspector access check failed")
        raise _safe_access_error() from None
    if result is not True:
        logger.warning("Tailora Inspector access check denied a request")
        raise _safe_access_error()


async def is_inspector_access_allowed(
    request: Any,
    access_check: AccessCheck | None,
) -> bool:
    """Swagger 문서에 Inspector plugin을 포함해도 되는지 반환한다."""
    try:
        await enforce_inspector_access(request, access_check)
    except HTTPException:
        return False
    return True


def create_inspector_access_dependency(access_check: AccessCheck):
    """FastAPI 라우터 전체에 적용할 접근 검사 dependency를 만든다."""

    async def require_inspector_access(request: Request) -> None:
        """현재 FastAPI 요청이 Inspector에 접근할 수 있는지 검사한다."""
        await enforce_inspector_access(request, access_check)

    return require_inspector_access
