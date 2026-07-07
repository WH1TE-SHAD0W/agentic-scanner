"""One mutable JSON file per job in data/jobs/. Saves are atomic (temp +
os.replace) because the UI reads the file while the worker thread updates it."""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from storage.paths import JOBS_DIR, UPLOADS_DIR


def create_job() -> dict:
    job = {
        "job_id": uuid.uuid4().hex,
        "created": now_iso(),
        "started": None,
        "finished": None,
        "state": "OPEN",
        "pages": [],
        "local_data": None,
        "cloud_data": None,
        "extracted_data": None,
        "conflicts": [],
        "one_liner": None,
        "error": None,
    }
    save(job)
    return job


def add_page(job: dict, file_storage) -> dict:
    """Saves the uploaded image under a fresh page_id and appends the page entry."""
    ext = Path(file_storage.filename).suffix.lower()
    page_id = uuid.uuid4().hex
    file_storage.save(UPLOADS_DIR / f"{page_id}{ext}")
    page = {
        "page_id": page_id,
        "filename": file_storage.filename,
        "ext": ext,
        "state": "PENDING",
        "route": None,
        "phi_confidence": None,
        "phi_reasoning": None,
        "extraction_retries": 0,
        "error": None,
    }
    job["pages"].append(page)
    return page


def load(job_id: str) -> dict | None:
    path = JOBS_DIR / f"{job_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save(job: dict) -> None:
    path = JOBS_DIR / f"{job['job_id']}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def list_jobs() -> list[dict]:
    files = sorted(JOBS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [json.loads(p.read_text(encoding="utf-8")) for p in files]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
