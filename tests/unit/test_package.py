"""Tailora 패키지의 기본 설치 상태를 확인한다."""


def test_tailora_package_can_be_imported():
    """Tailora 패키지를 불러올 수 있는지 확인한다."""
    import tailora

    assert tailora is not None
