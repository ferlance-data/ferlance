"""FastAPI application: wires routers, static frontend, and storage lifecycle.

Layout
------
- ``routers/``      HTTP layer, one module per product area.
- ``deps.py``       auth, tenancy, date-range and data-scope dependencies.
- ``dataset_store`` import persistence and the "which records count" rules.
- ``processor`` / ``universal_ingestion`` / ``sms_parser``  ingestion.
- ``analytics`` / ``insights``  deterministic metrics (the source of truth).
- ``llm`` / ``rag`` / ``market_research``  optional AI and web context.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, db
from .routers import admin, analytics, auth, datasets, financial_position, integrations, inventory, lance


@asynccontextmanager
async def lifespan(_: FastAPI):
    config.ensure_storage()
    db.initialize(config.DB_PATH)
    db.repair_dataset_paths(config.DB_PATH, config.RAW_DIR, config.PROCESSED_DIR)
    yield


app = FastAPI(title="Ferlance", version="0.2.0", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIR / "assets"), name="assets")
for module in (auth, admin, datasets, analytics, inventory, financial_position, integrations, lance):
    app.include_router(module.router)


@app.middleware("http")
async def revalidate_frontend(request: Request, call_next):
    """Unbundled ES modules have no content hashes, so make browsers revalidate (cheap 304s) after deploys."""
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


@app.get("/", response_class=FileResponse, include_in_schema=False)
def landing_page() -> Path:
    return config.FRONTEND_DIR / "landing.html"


@app.get("/app", response_class=FileResponse, include_in_schema=False)
def application() -> Path:
    return config.FRONTEND_DIR / "index.html"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
