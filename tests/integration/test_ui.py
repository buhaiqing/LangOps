"""Integration test for Web UI."""

from fastapi.testclient import TestClient

from langops.web.main import create_app


def test_ui_page_loads_with_static_assets() -> None:
    client = TestClient(create_app())

    index = client.get("/ui/")
    assert index.status_code == 200

    css = client.get("/ui/static/css/app.css")
    js = client.get("/ui/static/js/app.js")
    assert css.status_code == 200
    assert js.status_code == 200
