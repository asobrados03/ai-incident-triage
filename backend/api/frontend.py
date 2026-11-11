from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

# Prefijos que nunca son rutas del SPA. Las rutas de API que no coinciden con
# ninguna ruta registrada deben devolver 404, no index.html.
API_PREFIXES = frozenset(
    {
        "admin",
        "assets",
        "audit",
        "auth",
        "docs",
        "health",
        "incidents",
        "openapi.json",
        "redoc",
        "review-metrics",
        "users",
    },
)

# Prefijos que tampoco deben servirse como SPA en una navegación HTML.
# `/incidents/{id}` y `/users` se excluyen a propósito: son rutas del SPA y de
# la API, y se distinguen por la cabecera Accept.
NON_SPA_PREFIXES = frozenset(
    {
        "admin",
        "assets",
        "audit",
        "auth",
        "docs",
        "health",
        "openapi.json",
        "redoc",
        "review-metrics",
    },
)
NON_SPA_EXACT = frozenset({"/incidents", "/incidents/"})


def _is_file_within(root: Path, path: str) -> bool:
    candidate = (root / path.lstrip("/")).resolve()
    return candidate.is_file() and candidate.is_relative_to(root)


def _is_spa_navigation(path: str) -> bool:
    if path in NON_SPA_EXACT:
        return False
    if "." in path.rsplit("/", 1)[-1]:
        return False
    first_segment = path.strip("/").split("/", 1)[0]
    return first_segment not in NON_SPA_PREFIXES


def mount_frontend(app: FastAPI, dist_dir: Path = FRONTEND_DIST) -> bool:
    """Sirve el build de Vite y el fallback del SPA si el directorio existe."""
    index = dist_dir / "index.html"
    if not index.is_file():
        return False

    root = dist_dir.resolve()

    assets_dir = root / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.middleware("http")
    async def spa_navigation(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path
        accepts_html = "text/html" in request.headers.get("accept", "")
        if (
            request.method in {"GET", "HEAD"}
            and accepts_html
            and _is_spa_navigation(path)
            and not _is_file_within(root, path)
        ):
            return FileResponse(index)
        return await call_next(request)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def frontend_fallback(full_path: str) -> FileResponse:
        normalized = full_path.strip("/")
        first_segment = normalized.split("/", 1)[0]
        if first_segment in API_PREFIXES:
            raise HTTPException(status_code=404, detail="Not found")

        candidate = (root / normalized).resolve()
        if normalized and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        if normalized and "." in candidate.name:
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(index)

    return True
