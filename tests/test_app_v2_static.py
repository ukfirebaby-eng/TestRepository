from pathlib import Path

from fastapi.testclient import TestClient

import api


def test_legacy_root_still_serves_existing_ui():
    with TestClient(api.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Diamond Miner | Spatial Canvas" in response.text


def test_app_v2_serves_built_index_when_present(tmp_path, monkeypatch):
    app_v2_dir = tmp_path / "app-v2"
    app_v2_dir.mkdir()
    (app_v2_dir / "index.html").write_text(
        "<!doctype html><title>Diamond Miner Command Center</title><div id=\"root\"></div>",
        encoding="utf-8",
    )
    monkeypatch.setattr(api, "APP_V2_DIR", app_v2_dir)

    with TestClient(api.app) as client:
        response = client.get("/app-v2")

    assert response.status_code == 200
    assert "Diamond Miner Command Center" in response.text


def test_app_v2_index_is_not_cached_between_rebuilds(tmp_path, monkeypatch):
    app_v2_dir = tmp_path / "app-v2"
    app_v2_dir.mkdir()
    (app_v2_dir / "index.html").write_text(
        "<!doctype html><script src=\"/app-v2/assets/index-new.js\"></script>",
        encoding="utf-8",
    )
    monkeypatch.setattr(api, "APP_V2_DIR", app_v2_dir)

    with TestClient(api.app) as client:
        response = client.get("/app-v2")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"
    assert response.headers["pragma"] == "no-cache"


def test_app_v2_asset_route_serves_built_assets(tmp_path, monkeypatch):
    app_v2_dir = tmp_path / "app-v2"
    asset_dir = app_v2_dir / "assets"
    asset_dir.mkdir(parents=True)
    (asset_dir / "app.js").write_text("console.log('v2');", encoding="utf-8")
    monkeypatch.setattr(api, "APP_V2_DIR", app_v2_dir)

    with TestClient(api.app) as client:
        response = client.get("/app-v2/assets/app.js")

    assert response.status_code == 200
    assert "console.log('v2')" in response.text
