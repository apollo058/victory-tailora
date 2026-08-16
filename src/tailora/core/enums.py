"""코어 이벤트에서 사용하는 공통 열거형을 제공한다."""

from enum import Enum


class Framework(str, Enum):
    """이벤트를 만든 웹 프레임워크를 나타낸다."""

    FASTAPI = "fastapi"
