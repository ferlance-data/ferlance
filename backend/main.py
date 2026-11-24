"""FastAPI application: wires routers, static frontend, and storage lifecycle.

Layout
------
- ``routers/``      HTTP layer, one module per product area.
- ``deps.py``       auth, tenancy, date-range and data-scope dependencies.
- ``dataset_store`` import persistence and the "which records count" rules.
- ``processor`` / ``universal_ingestion`` / ``sms_parser``  ingestion.
- ``analytics`` / ``insights``  deterministic metrics (the source of truth).
- ``llm`` / ``rag`` / ``news_context``  optional AI and free news context; ``advisor`` builds plain-language advice.
"""

import os
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import config, dataset_store, db, exports
from .routers import admin, admin_auth, analytics, auth, books, datasets, debts, invoices, pages, financial_position, inventory, lance, team


@asynccontextmanager
async def lifespan(_: FastAPI):
    config.require_production_secret()
    config.ensure_storage()
    db.initialize(config.DB_PATH)
    db.repair_dataset_paths(config.DB_PATH, config.RAW_DIR, config.PROCESSED_DIR)
    dataset_store.backfill_periods()
    scheduler = exports.start()
    yield
    if scheduler:
        scheduler[1].set()


class _BuildAssets(StaticFiles):
    """Static files that answer 404 (not a 500 from Starlette's directory check) until the first build."""

    async def __call__(self, scope, receive, send):
        if not os.path.isdir(self.directory):
            await Response(status_code=404)(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


app = FastAPI(title="Ferlance", version="1.15.0", lifespan=lifespan)
# The React frontend is a Vite build (frontend/dist). check_dir=False keeps the API
# importable before the first build; pages then explain how to build instead.
app.mount("/assets", _BuildAssets(directory=config.FRONTEND_DIST / "assets", check_dir=False), name="assets")
for module in (auth, admin_auth, admin, datasets, analytics, inventory, financial_position, books, debts, invoices, pages, lance, team):
    app.include_router(module.router)
app.include_router(team.public)

# Vite names bundles like app-CTxM_byd.js: the hash changes whenever the content does.
_HASHED_ASSET = re.compile(r"-[A-Za-z0-9_-]{8}\.(?:js|css|woff2?|svg|png|jpg|webp)$")


@app.middleware("http")
async def cache_policy(request: Request, call_next):
    """Hashed bundles never change, so cache them for a year; everything else (HTML) revalidates."""
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/api/"):
        return response
    if path.startswith("/assets/") and response.status_code == 200 and _HASHED_ASSET.search(path):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


class _Compression:
    """Gzip bundles, HTML and API JSON (about a third of the bytes on mobile data).

    Auth responses carry tokens and are left uncompressed, so their size can never be used
    to guess a secret (BREACH-style attacks).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.plain = app
        self.gzip = GZipMiddleware(app, minimum_size=1024)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].startswith("/api/auth/"):
            await self.plain(scope, receive, send)
        else:
            await self.gzip(scope, receive, send)


app.add_middleware(_Compression)


_BUILD_MISSING = """<!doctype html><title>Ferlance frontend not built</title>
<p>The Ferlance frontend has not been built yet. Run <code>npm --prefix frontend ci &amp;&amp; npm --prefix frontend run build</code>,
then reload this page.</p>"""


def _page(relative: str) -> Response:
    page = config.FRONTEND_DIST / relative
    if not page.is_file():
        return HTMLResponse(_BUILD_MISSING, status_code=503)
    return FileResponse(page)


@app.get("/", include_in_schema=False)
def landing_page() -> Response:
    return _page("index.html")


@app.get("/admin", include_in_schema=False)
@app.get("/admin/{_path:path}", include_in_schema=False)
def admin_console(_path: str = "") -> Response:
    """The admin console: its own sign-in and pages, separate from the business workspace."""
    return _page("admin/index.html")


@app.get("/app/admin", include_in_schema=False)
def old_admin_page() -> Response:
    return RedirectResponse("/admin", status_code=308)


@app.get("/app", include_in_schema=False)
@app.get("/app/{_path:path}", include_in_schema=False)
def application(_path: str = "") -> Response:
    """Every workspace route (/app/overview, /app/products, …) loads the same single-page app."""
    return _page("app/index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
