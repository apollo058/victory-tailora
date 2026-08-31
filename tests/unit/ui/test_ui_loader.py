"""Tailora UI 정적 자산 로더의 동작을 검증하는 단위 테스트."""

import pytest

from tailora.ui.loader import (
    get_inspector_asset,
    render_inspector_index,
)


def test_render_inspector_index_replaces_base_path():
    """index.html 템플릿 로드 시 지정된 base_path가 올바르게 주입되는지 확인한다."""
    html = render_inspector_index(base_path="/custom_inspector")
    assert '<meta name="tailora-base-path" content="/custom_inspector">' in html
    assert "<!doctype html>" in html.lower()
    assert "Tailora Inspector" in html


def test_get_inspector_asset_html():
    """index.html 자산 조회 시 올바른 HTML 내용과 Content-Type을 반환하는지 확인한다."""
    content, content_type = get_inspector_asset("index.html", base_path="/__tailora")
    assert "text/html; charset=utf-8" in content_type
    assert '<meta name="tailora-base-path" content="/__tailora">' in content


def test_get_inspector_asset_css():
    """styles.css 자산 조회 시 올바른 CSS 내용과 Content-Type을 반환하는지 확인한다."""
    content, content_type = get_inspector_asset("styles.css")
    assert "text/css; charset=utf-8" in content_type
    assert len(content) > 0


def test_get_inspector_asset_js():
    """app.js 자산 조회 시 올바른 JS 내용과 Content-Type을 반환하는지 확인한다."""
    content, content_type = get_inspector_asset("app.js")
    assert "application/javascript; charset=utf-8" in content_type
    assert len(content) > 0


def test_get_inspector_asset_not_found():
    """존재하지 않는 자산 요청 시 FileNotFoundError가 발생하는지 확인한다."""
    with pytest.raises(FileNotFoundError):
        get_inspector_asset("non_existent_asset.svg")


def test_get_inspector_asset_path_traversal_prevention():
    """상위 디렉터리 경로 접근 시도시 FileNotFoundError를 발생시키는지 확인한다."""
    with pytest.raises(FileNotFoundError):
        get_inspector_asset("../loader.py")
