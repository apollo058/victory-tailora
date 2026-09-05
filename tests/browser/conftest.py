"""실제 브라우저 테스트에 사용할 FastAPI 예제 서버 fixture를 제공한다."""

import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest
from playwright.sync_api import Page, sync_playwright


def _find_available_port() -> int:
    """로컬에서 현재 사용할 수 있는 TCP 포트를 하나 찾는다."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def _start_example_server(port: int) -> subprocess.Popen[bytes]:
    """브라우저 테스트용 FastAPI 예제 서버 프로세스를 시작한다."""
    project_root = Path(__file__).resolve().parents[2]
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "examples.fastapi.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    return subprocess.Popen(
        command,
        cwd=project_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def _wait_for_server(base_url: str, process: subprocess.Popen[bytes]) -> None:
    """예제 서버가 요청을 처리할 때까지 제한된 시간 동안 대기한다."""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                "브라우저 테스트용 FastAPI 서버가 시작 중 종료되었습니다."
            )
        try:
            with urlopen(f"{base_url}/health", timeout=0.5) as response:
                if response.status == 200:
                    return
        except URLError:
            time.sleep(0.1)
    raise RuntimeError(
        "브라우저 테스트용 FastAPI 서버가 시간 안에 준비되지 않았습니다."
    )


def _stop_example_server(process: subprocess.Popen[bytes]) -> None:
    """종료되지 않은 예제 서버 프로세스를 안전하게 중지한다."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


@pytest.fixture(scope="session")
def live_example_url() -> Iterator[str]:
    """실제 FastAPI 예제를 제공하는 로컬 URL을 테스트 세션 동안 반환한다."""
    port = _find_available_port()
    process = _start_example_server(port)
    base_url = f"http://127.0.0.1:{port}"
    _wait_for_server(base_url, process)
    try:
        yield base_url
    finally:
        _stop_example_server(process)


@pytest.fixture
def browser_page() -> Iterator[Page]:
    """각 브라우저 테스트 후 완전히 종료되는 Chromium 페이지를 제공한다."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        try:
            yield page
        finally:
            browser.close()
