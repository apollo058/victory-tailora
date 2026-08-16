"""문자열과 목록의 크기를 제한하는 유틸리티를 제공한다."""

TRUNCATION_MARKER: str = " \u2026[truncated]"


def _validate_limit(value: int, field_name: str) -> int:
    """제한값이 0 이상인 정수인지 확인한다."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def truncate_str(value: str | None, max_length: int) -> str | None:
    """문자열이 최대 길이를 초과하면 잘라내고 마커를 추가한다.

    잘린 값에는 ' …[truncated]' 표시가 붙는다.
    value가 None이면 None을 반환한다.
    """
    if value is None:
        return None
    max_length = _validate_limit(max_length, "max_length")
    if len(value) <= max_length:
        return value
    if max_length < len(TRUNCATION_MARKER):
        return TRUNCATION_MARKER[:max_length]
    cut = max(0, max_length - len(TRUNCATION_MARKER))
    return value[:cut] + TRUNCATION_MARKER


def truncate_list(items: list, max_count: int) -> tuple[list, bool]:
    """목록이 최대 개수를 초과하면 앞에서부터 자르고 잘림 여부를 함께 반환한다."""
    max_count = _validate_limit(max_count, "max_count")
    if len(items) <= max_count:
        return list(items), False
    return list(items[:max_count]), True
