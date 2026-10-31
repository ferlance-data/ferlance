"""FastAPI application: wires routers, static frontend, and storage lifecycle.

Layout
-------
- ``routers/``      HTTP layer, one module per product area.
- ``deps.py``       auth, tenancy, date-range and data-scope dependencies.
- ``dataset_store`` import persistence and the "which records count" rules.
- ``processor`` / ``folder_imports`` / ``sms_parser``  ingestion.
- ``analytics`` / ``insights``  deterministic metrics (the source of truth).
- ``llm`` / ``rag`` / ``market_research``  optional AI and web context.
"""

import hashlib
import logging
import shutil
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, db, dataset_store
from .folder_imports import FolderImporter
from .processor import process_file
from .routers import admin, analytics, auth, datasets, financial_position, integrations, inventory, lance

logger = logging.getLogger(__name__)


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def import_watched_file(business_id: str, source_path: Path) -> dict:
    """Copy an inbox workbook into raw storage and register it as a dataset."""
    suffix = source_path.suffix.lower()
    if source_path.stat().st_size > config.MAX_UPLOAD_BYTES:
        raise ValueError("File is larger than the 10 MB upload limit.")
    dataset_id = dataset_store.new_id()
    raw_path = config.RAW_DIR / f"{dataset_id}{suffix}"
    shutil.copyfile(source_path, raw_path)
    result = process_file(raw_path, suffix)
    dataset = dataset_store.save(business_id, dataset_id, source_path.name, suffix, raw_path, result, _checksum(raw_path))
    return {"id": dataset["id"], "status": dataset["status"], "errors": dataset["errors"]}


@asynccontextmanager
async def lifespan(_: FastAPI):
    stop_event = threading.Event()
    importer = FolderImporter(config.IMPORT_DIR, config.DB_PATH, import_watched_file)
    worker = threading.Thread(target=importer.run, args=(stop_event,), name="excel-folder-importer", daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop_event.set()
        worker.join(timeout=10)


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
