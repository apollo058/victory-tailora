"""격리된 설치 대상에서 Tailora wheel의 실제 실행 흐름을 확인한다."""

from importlib.util import find_spec
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _build_distributions(output_dir: Path) -> list[Path]:
    """프로젝트를 별도 출력 디렉터리에 wheel과 sdist로 빌드한다."""
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


def _runtime_environment(install_dir: Path) -> dict[str, str]:
    """현재 checkout과 site-packages를 제외한 실행 환경을 만든다."""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(install_dir)
    return environment


def _find_available_port() -> int:
    """로컬에서 현재 사용할 수 있는 TCP 포트를 하나 찾는다."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def _wait_for_server(base_url: str, process: subprocess.Popen[bytes]) -> None:
    """격리된 예제 서버가 요청을 처리할 때까지 제한 시간 동안 대기한다."""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            error = process.stderr.read().decode() if process.stderr else ""
            raise AssertionError(f"예제 서버가 시작 중 종료되었습니다.\n{error}")
        try:
            with urlopen(f"{base_url}/health", timeout=0.5) as response:
                if response.status == 200:
                    return
        except URLError:
            time.sleep(0.1)
    raise AssertionError("예제 서버가 제한 시간 안에 준비되지 않았습니다.")


def _stop_server(process: subprocess.Popen[bytes]) -> None:
    """테스트가 시작한 예제 서버를 안전하게 종료한다."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _get_response(base_url: str, path: str) -> tuple[int, bytes]:
    """예제 서버의 응답 상태 코드와 본문을 반환한다."""
    with urlopen(f"{base_url}{path}", timeout=5) as response:
        return response.status, response.read()


def _install_wheel(wheel: Path, install_dir: Path, cwd: Path) -> None:
    """wheel과 FastAPI·SQLAlchemy 선택 의존성을 격리 경로에 설치한다."""
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--target",
            str(install_dir),
            f"{wheel}[fastapi,sqlalchemy]",
        ],
        check=True,
        cwd=cwd,
    )


def _assert_installed_package_version(
    environment: dict[str, str],
    cwd: Path,
) -> None:
    """checkout 밖에서 설치된 Tailora package의 버전을 확인한다."""
    import_result = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            "import tailora; print(tailora.__version__)",
        ],
        check=True,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert import_result.stdout.strip() == "0.1.0rc1"


def _start_example_server(
    port: int,
    environment: dict[str, str],
) -> subprocess.Popen[bytes]:
    """격리된 의존성으로 FastAPI 예제 서버를 시작한다."""
    return subprocess.Popen(
        [
            sys.executable,
            "-S",
            "-m",
            "uvicorn",
            "examples.fastapi.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def _assert_example_flow(base_url: str) -> None:
    """예제 사용자 조회와 Swagger·Inspector API 흐름을 확인한다."""
    status, body = _get_response(base_url, "/users/1")
    assert status == 200
    assert json.loads(body) == {"id": "1", "name": "Alice"}

    status, body = _get_response(base_url, "/docs")
    assert status == 200
    assert b"Tailora" in body

    status, body = _get_response(base_url, "/__tailora/health")
    assert status == 200
    assert json.loads(body)["status"] == "ok"

    status, body = _get_response(base_url, "/__tailora/requests")
    assert status == 200
    assert json.loads(body)["count"] >= 1


def test_built_wheel_runs_example_outside_checkout(tmp_path: Path):
    """wheel과 선택 의존성을 격리 설치한 뒤 예제의 진단 흐름을 실행한다."""
    if find_spec("build") is None:
        pytest.skip("release extra(build)가 설치되지 않았습니다.")

    distributions = _build_distributions(tmp_path / "dist")
    wheel = next(path for path in distributions if path.suffix == ".whl")
    install_dir = tmp_path / "installed"
    environment = _runtime_environment(install_dir)
    _install_wheel(wheel, install_dir, tmp_path)
    _assert_installed_package_version(environment, tmp_path)

    port = _find_available_port()
    process = _start_example_server(port, environment)
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_server(base_url, process)
        _assert_example_flow(base_url)
    finally:
        _stop_server(process)
