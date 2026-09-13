"""Tailora 패키지의 설치와 릴리스 메타데이터를 확인한다."""

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib


def _load_project_metadata() -> dict:
    """프로젝트의 pyproject 메타데이터를 읽어 반환한다."""
    project_root = Path(__file__).resolve().parents[2]
    return tomllib.loads(
        (project_root / "pyproject.toml").read_text(encoding="utf-8"),
    )


def test_tailora_package_can_be_imported():
    """Tailora 패키지를 불러올 수 있는지 확인한다."""
    import tailora

    assert tailora is not None


def test_package_version_matches_project_metadata():
    """패키지 버전과 pyproject 프로젝트 버전이 일치하는지 확인한다."""
    import tailora

    metadata = _load_project_metadata()

    assert tailora.__version__ == metadata["project"]["version"]


def test_release_extra_contains_reproducible_distribution_tools():
    """release extra가 wheel 검증에 필요한 도구를 제공하는지 확인한다."""
    metadata = _load_project_metadata()
    release_extra = metadata["project"]["optional-dependencies"]["release"]

    assert any(item.startswith("build==") for item in release_extra)
    assert any(item.startswith("twine==") for item in release_extra)


def test_dev_extra_supports_python_310_metadata_tests():
    """dev extra가 Python 3.10용 TOML parser를 제공하는지 확인한다."""
    metadata = _load_project_metadata()
    dev_extra = metadata["project"]["optional-dependencies"]["dev"]

    assert any(
        item.startswith("tomli>=") and "python_version < '3.11'" in item
        for item in dev_extra
    )


def test_release_documents_are_present():
    """릴리스에 필요한 라이선스와 변경 기록 문서가 저장소에 있는지 확인한다."""
    project_root = Path(__file__).resolve().parents[2]

    assert (project_root / "LICENSE").is_file()
    assert (project_root / "CHANGELOG.md").is_file()
