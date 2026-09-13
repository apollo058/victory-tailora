"""Tailora 배포 파일의 경계와 메타데이터를 확인한다."""

from pathlib import Path
import subprocess
import sys
import tarfile
import zipfile

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _build_distributions(output_dir: Path) -> list[Path]:
    """프로젝트를 별도 출력 디렉터리에 wheel과 sdist로 빌드한다."""
    if __import__("importlib.util").util.find_spec("build") is None:
        pytest.skip("release extra(build)가 설치되지 않았습니다.")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--outdir",
            str(output_dir),
            str(PROJECT_ROOT),
        ],
        check=True,
        cwd=PROJECT_ROOT,
    )
    return sorted(output_dir.iterdir())


def test_distributions_exclude_repository_examples_and_tests(tmp_path: Path):
    """wheel과 sdist가 라이브러리 경계 밖의 예제와 테스트를 포함하지 않는지 확인한다."""
    distributions = _build_distributions(tmp_path / "dist")

    assert {path.suffix for path in distributions} == {".whl", ".gz"}
    wheel = next(path for path in distributions if path.suffix == ".whl")
    source_archive = next(path for path in distributions if path.suffix == ".gz")

    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert any(name.startswith("tailora/") for name in names)
        assert not any(name.startswith(("examples/", "tests/")) for name in names)
        assert not any(name.endswith((".sqlite", ".db", ".env")) for name in names)

    with tarfile.open(source_archive) as archive:
        names = archive.getnames()
        assert any(name.endswith("/CHANGELOG.md") for name in names)
        assert any(name.endswith("/docs/quickstart.md") for name in names)
        assert not any("/examples/" in name for name in names)
        assert not any("/tests/" in name for name in names)
        assert not any(name.endswith((".sqlite", ".db", ".env")) for name in names)
