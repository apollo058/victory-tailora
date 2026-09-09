"""FastAPI Inspector 접근 hook의 fail-closed 동작을 검증한다."""

import pytest
from fastapi import HTTPException

from tailora.adapters.fastapi.security import enforce_inspector_access


@pytest.mark.asyncio
async def test_sync_access_check_can_allow_request():
    """동기 접근 hook이 True를 반환하면 요청을 허용하는지 확인한다."""
    request = object()

    def allow(received_request):
        """받은 요청이 기대한 객체인지 확인한다."""
        return received_request is request

    await enforce_inspector_access(request, allow)


@pytest.mark.asyncio
async def test_async_access_check_can_allow_request():
    """비동기 접근 hook이 True를 반환하면 요청을 허용하는지 확인한다."""

    async def allow(request):
        """비동기 테스트 요청을 허용한다."""
        return request is not None

    await enforce_inspector_access(object(), allow)


@pytest.mark.asyncio
async def test_false_access_result_is_denied():
    """접근 hook이 False를 반환하면 403으로 거부하는지 확인한다."""

    def deny(request):
        """테스트 요청을 거부한다."""
        return False

    with pytest.raises(HTTPException) as caught:
        await enforce_inspector_access(object(), deny)

    assert caught.value.status_code == 403
    assert caught.value.detail == "Inspector access denied."


@pytest.mark.asyncio
async def test_authentication_status_is_preserved_but_detail_is_replaced():
    """hook의 401·403은 유지하되 민감한 detail은 공개하지 않는지 확인한다."""

    def deny(request):
        """민감한 detail이 포함된 401 오류를 발생시킨다."""
        raise HTTPException(status_code=401, detail="token=super-secret")

    with pytest.raises(HTTPException) as caught:
        await enforce_inspector_access(object(), deny)

    assert caught.value.status_code == 401
    assert caught.value.detail == "Inspector authentication required."
    assert "super-secret" not in str(caught.value.detail)


@pytest.mark.asyncio
async def test_access_check_exception_fails_closed_without_secret(caplog):
    """hook 예외를 403으로 차단하고 비밀값을 로그에 남기지 않는지 확인한다."""

    def broken(request):
        """민감한 문구를 포함한 예외를 발생시킨다."""
        raise RuntimeError("password=super-secret")

    with pytest.raises(HTTPException) as caught:
        await enforce_inspector_access(object(), broken)

    assert caught.value.status_code == 403
    assert "super-secret" not in caplog.text


@pytest.mark.asyncio
async def test_non_boolean_access_result_fails_closed():
    """hook이 bool 이외의 값을 반환하면 접근을 거부하는지 확인한다."""

    def invalid(request):
        """허용 여부가 아닌 문자열을 반환한다."""
        return "yes"

    with pytest.raises(HTTPException) as caught:
        await enforce_inspector_access(object(), invalid)

    assert caught.value.status_code == 403
