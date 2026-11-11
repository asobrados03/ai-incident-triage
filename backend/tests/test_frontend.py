from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.frontend import mount_frontend

HTML = {"Accept": "text/html,application/xhtml+xml"}
INDEX = '<div id="root"></div>'


def make_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX, encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('ok')", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg></svg>", encoding="utf-8")
    return dist


def test_mount_frontend_serves_index_assets_and_spa_routes(tmp_path: Path) -> None:
    app = FastAPI()
    assert mount_frontend(app, make_dist(tmp_path)) is True
    client = TestClient(app)

    root = client.get("/")
    assert root.status_code == 200
    assert INDEX in root.text

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert metrics.text == root.text

    asset = client.get("/assets/app.js")
    assert asset.status_code == 200
    assert asset.text == "console.log('ok')"

    icon = client.get("/favicon.svg")
    assert icon.status_code == 200
    assert icon.text == "<svg></svg>"

    missing_asset = client.get("/assets/missing.js")
    assert missing_asset.status_code == 404


def test_mount_frontend_serves_spa_on_html_navigation(tmp_path: Path) -> None:
    app = FastAPI()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    assert mount_frontend(app, make_dist(tmp_path)) is True
    client = TestClient(app)

    # Rutas que existen tanto en el SPA como en la API: una navegación del
    # navegador debe recibir index.html, no el JSON de la API.
    for path in ("/incidents/00000000-0000-0000-0000-000000000000", "/users"):
        response = client.get(path, headers=HTML)
        assert response.status_code == 200
        assert INDEX in response.text

    assert client.get("/incidents", headers=HTML).status_code == 404
    assert client.get("/missing.js", headers=HTML).status_code == 404
    assert client.get("/health", headers=HTML).json() == {"status": "ok"}
    docs = client.get("/docs", headers=HTML)
    assert docs.status_code == 200
    assert "swagger-ui" in docs.text


def test_mount_frontend_does_not_shadow_api_or_docs(tmp_path: Path) -> None:
    app = FastAPI()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    assert mount_frontend(app, make_dist(tmp_path)) is True
    client = TestClient(app)

    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/auth/unknown").status_code == 404
    assert client.get("/incidents/unknown").status_code == 404
    assert client.get("/users").status_code == 404
    assert client.get("/missing.js").status_code == 404


def test_mount_frontend_skips_when_dist_is_missing(tmp_path: Path) -> None:
    app = FastAPI()

    assert mount_frontend(app, tmp_path / "missing") is False
    assert TestClient(app).get("/").status_code == 404
