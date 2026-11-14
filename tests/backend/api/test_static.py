# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.static import mount_static


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def test_serves_index_and_keeps_api(tmp_path: Path):
    (tmp_path / "index.html").write_text("<h1>hi</h1>")
    app = _app()
    assert mount_static(app, tmp_path) is True
    c = TestClient(app)
    assert "hi" in c.get("/").text
    assert c.get("/health").json() == {"status": "ok"}
    assert c.get("/nope.js").status_code == 404


def test_no_dir_is_noop(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("STATIC_DIR", raising=False)
    app = _app()
    assert mount_static(app) is False
    assert mount_static(app, tmp_path / "missing") is False


def test_env_var(tmp_path: Path, monkeypatch):
    (tmp_path / "index.html").write_text("x")
    monkeypatch.setenv("STATIC_DIR", str(tmp_path))
    assert mount_static(_app()) is True


def test_no_path_traversal(tmp_path: Path):
    (tmp_path / "pub").mkdir()
    (tmp_path / "pub" / "index.html").write_text("x")
    (tmp_path / "secret.txt").write_text("s3cret")
    app = _app()
    mount_static(app, tmp_path / "pub")
    assert "s3cret" not in TestClient(app).get("/..%2fsecret.txt").text


def _spa(tmp_path: Path) -> TestClient:
    (tmp_path / "pub" / "assets").mkdir(parents=True)
    (tmp_path / "pub" / "index.html").write_text("<h1>spa</h1>")
    (tmp_path / "pub" / "assets" / "a-1.js").write_text("x=1")
    (tmp_path / "secret.txt").write_text("s3cret")
    (tmp_path / "pub" / "link").symlink_to(tmp_path / "secret.txt")
    (tmp_path / "pub" / "dirlink").symlink_to(tmp_path)
    app = _app()
    mount_static(app, tmp_path / "pub")
    return TestClient(app)


def test_spa_fallback_for_deep_links(tmp_path: Path):
    c = _spa(tmp_path)
    for p in ("/chat", "/telemetry/abc", "/chat/"):
        r = c.get(p)
        assert r.status_code == 200 and "spa" in r.text, p
    assert "spa" in c.get("/chat", headers={"Accept": "text/html"}).text
    assert c.head("/chat").status_code == 200


def test_no_fallback_for_api_assets_files_and_methods(tmp_path: Path):
    c = _spa(tmp_path)
    for p in ("/api/unknown", "/api", "/health/x", "/assets/missing-2.js", "/missing.js", "/x.png"):
        r = c.get(p)
        assert r.status_code == 404 and "spa" not in r.text, p
    assert c.get("/api/unknown").json() == {"detail": "Not Found"}
    assert c.post("/chat").status_code in (404, 405)
    assert "spa" not in c.post("/chat").text


def test_traversal_and_symlink_never_leak(tmp_path: Path):
    c = _spa(tmp_path)
    for p in (
        "/..%2fsecret.txt",
        "/%2e%2e/secret.txt",
        "/%2e%2e%2fsecret.txt",
        "/link",
        "/dirlink/secret.txt",
        "/assets/../../secret.txt",
    ):
        assert "s3cret" not in c.get(p).text, p


def test_cache_headers(tmp_path: Path):
    c = _spa(tmp_path)
    assert c.get("/assets/a-1.js").headers["cache-control"] == (
        "public, max-age=31536000, immutable"
    )
    assert c.get("/").headers["cache-control"] == "no-cache"
    assert c.get("/chat").headers["cache-control"] == "no-cache"
