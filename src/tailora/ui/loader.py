"""UI 정적 자산 로딩 및 템플릿 렌더링 유틸리티."""

import importlib.resources
import posixpath

CONTENT_TYPES: dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
}

ALLOWED_ASSETS: set[str] = {
    "index.html",
    "styles.css",
    "app.js",
    "swagger-plugin.css",
    "swagger-plugin.js",
}


def render_inspector_index(base_path: str = "/__tailora") -> str:
    """기본 index.html 템플릿을 읽고 base_path 메타 태그를 주입하여 반환한다."""
    normalized_base = base_path.rstrip("/")
    if not normalized_base:
        normalized_base = ""

    resource_files = importlib.resources.files("tailora.ui.inspector")
    raw_html = resource_files.joinpath("index.html").read_text(encoding="utf-8")

    # {{BASE_PATH}} 플레이스홀더를 현재 API 접두사로 치환
    return raw_html.replace("{{BASE_PATH}}", normalized_base)


def get_inspector_asset(
    filename: str,
    base_path: str = "/__tailora",
) -> tuple[str, str]:
    """요청된 정적 자산의 내용과 Content-Type 헤더 값을 반환한다."""
    # 경로 순회(Path Traversal) 방지: 정규화 및 허용된 파일명 검사
    clean_name = posixpath.normpath(filename)
    if clean_name not in ALLOWED_ASSETS:
        raise FileNotFoundError(f"Asset '{filename}' not found or not allowed")

    if clean_name == "index.html":
        content = render_inspector_index(base_path=base_path)
        return content, CONTENT_TYPES[".html"]

    ext = posixpath.splitext(clean_name)[1]
    content_type = CONTENT_TYPES.get(ext, "application/octet-stream")

    resource_files = importlib.resources.files("tailora.ui.inspector")
    target_file = resource_files.joinpath(clean_name)
    if not target_file.is_file():
        raise FileNotFoundError(f"Asset file '{clean_name}' does not exist")

    content = target_file.read_text(encoding="utf-8")
    return content, content_type
