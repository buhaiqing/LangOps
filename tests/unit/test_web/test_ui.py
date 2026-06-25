"""Web UI static assets tests."""

from pathlib import Path

from fastapi.testclient import TestClient

from langops.web.main import STATIC_DIR, create_app


def test_static_dir_exists() -> None:
    assert STATIC_DIR.is_dir()
    assert (STATIC_DIR / "index.html").is_file()
    assert (STATIC_DIR / "css" / "app.css").is_file()
    assert (STATIC_DIR / "js" / "app.js").is_file()


def test_ui_index_returns_html() -> None:
    client = TestClient(create_app())
    response = client.get("/ui")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "LangOps" in response.text
    assert "修复审批" in response.text
    assert "/ui/static/css/app.css" in response.text


def test_ui_js_references_remediation_api() -> None:
    js = (STATIC_DIR / "js" / "app.js").read_text(encoding="utf-8")
    assert "/api/v1/remediation" in js
    assert "initRemediationPanel" in js


def test_ui_static_css_served() -> None:
    client = TestClient(create_app())
    response = client.get("/ui/static/css/app.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
    assert "--accent" in response.text


def test_root_includes_ui_link() -> None:
    client = TestClient(create_app())
    response = client.get("/")
    assert response.json()["ui"] == "/ui"
