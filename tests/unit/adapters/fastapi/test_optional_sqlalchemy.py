"""SQLAlchemy 선택 의존성의 격리 동작을 확인한다."""

from fastapi import FastAPI
import pytest

from tailora.adapters.fastapi import enable_inspector
from tailora.core.store import RingBuffer


def test_enable_inspector_without_engine():
    """엔진 없이 호출 시 SQLAlchemy 없이도 정상 동작하는지 확인한다."""
    app = FastAPI()
    store = enable_inspector(app)

    assert isinstance(store, RingBuffer)


def test_lazy_attribute_access_nonexistent():
    """존재하지 않는 속성 접근 시 AttributeError가 발생하는지 확인한다."""
    import tailora.adapters.fastapi as adapter

    with pytest.raises(AttributeError, match="has no attribute 'nonexistent'"):
        _ = adapter.nonexistent

