import hashlib
import logging
import threading
from pathlib import Path
from typing import Any, Callable

from . import db

logger = logging.getLogger(__name__)


class FolderImporter:
    def __init__(
        self,
        import_dir: Path,
        db_path: Path,
        import_file: Callable[[str, Path], dict[str, Any]],
        interval_seconds: float = 5,
    ) -> None:
        self.import_dir = import_dir
        self.db_path = db_path
        self.import_file = import_file
        self.interval_seconds = interval_seconds
        self._observed: dict[Path, tuple[int, int]] = {}

    def run(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            try:
                self.scan_once()
            except Exception:
                logger.exception("Excel import folder scan failed.")
            stop_event.wait(self.interval_seconds)

    def scan_once(self) -> None:
        businesses = db.many(self.db_path, "SELECT id FROM businesses")
        self.import_dir.mkdir(parents=True, exist_ok=True)
        for business in businesses:
            business_id = business["id"]
            folder = self.import_dir / business_id
            folder.mkdir(parents=True, exist_ok=True)
            for path in folder.iterdir():
                if not path.is_file() or path.suffix.lower() != ".xlsx" or path.name.startswith("~$"):
                    continue
                try:
                    self._process_if_ready(business_id, path)
                except Exception:
                    logger.exception("Could not import Excel file %s.", path)

    def _process_if_ready(self, business_id: str, path: Path) -> None:
        stat = path.stat()
        signature = (stat.st_size, stat.st_mtime_ns)
        if self._observed.get(path) != signature:
            self._observed[path] = signature
            return

        checksum = _file_checksum(path)
        current_stat = path.stat()
        if (current_stat.st_size, current_stat.st_mtime_ns) != signature:
            self._observed[path] = (current_stat.st_size, current_stat.st_mtime_ns)
            return

        previous = db.one(
            self.db_path,
            "SELECT file_size, modified_ns, checksum FROM folder_imports WHERE business_id = ? AND filename = ?",
            (business_id, path.name),
        )
        if previous and previous["checksum"] == checksum:
            return

        try:
            result = self.import_file(business_id, path)
            status = result["status"]
            error = "; ".join(result["errors"])
            dataset_id = result["id"]
        except Exception as exc:
            logger.exception("Excel file import failed for %s.", path)
            status = "failed"
            error = str(exc)[:1000] or exc.__class__.__name__
            dataset_id = None

        db.insert(
            self.db_path,
            """
            INSERT INTO folder_imports
                (business_id, filename, file_size, modified_ns, checksum, status, error, dataset_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(business_id, filename) DO UPDATE SET
                file_size = excluded.file_size,
                modified_ns = excluded.modified_ns,
                checksum = excluded.checksum,
                status = excluded.status,
                error = excluded.error,
                dataset_id = excluded.dataset_id,
                updated_at = excluded.updated_at
            """,
            (
                business_id,
                path.name,
                signature[0],
                signature[1],
                checksum,
                status,
                error,
                dataset_id,
                db.now(),
            ),
        )


def _file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
