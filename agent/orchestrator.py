import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from enum import Enum
from pathlib import Path

import config
from agent import tools
from schemas import excel_column_map
from schemas.birth_number import age_from_birth_number
from storage import job_store
from storage.paths import CLOUD_DIR, LOCAL_DIR, find_page_image


class JobState(str, Enum):
    OPEN = "OPEN"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


class PageState(str, Enum):
    PENDING = "PENDING"
    CLASSIFYING = "CLASSIFYING"
    EXTRACTING = "EXTRACTING"
    DONE = "DONE"
    FAILED = "FAILED"


def start_job(job: dict) -> None:
    """Flips the job to RUNNING and processes it in a daemon thread — Flask
    stays sync, the job page polls the job file for progress."""
    job["state"] = JobState.RUNNING.value
    job["started"] = job_store.now_iso()
    job_store.save(job)
    threading.Thread(target=_run_job, args=(job["job_id"],), daemon=True).start()


def _run_job(job_id: str) -> None:
    job = job_store.load(job_id)
    try:
        _process(job)
    except Exception as e:  # the worker must never die silently
        job["state"] = JobState.FAILED.value
        job["error"] = f"unexpected worker error: {e}"
        job["finished"] = job_store.now_iso()
        job_store.save(job)


def _process(job: dict) -> None:
    job_id = job["job_id"]

    # 1. classify pages sequentially (LM Studio serves one request at a time)
    for page in job["pages"]:
        page["state"] = PageState.CLASSIFYING.value
        job_store.save(job)
        phi = tools.phi_classify(job_id, page["page_id"], _page_path(page))
        page["phi_confidence"] = phi.confidence
        page["phi_reasoning"] = phi.reasoning
        page["route"] = (
            "local" if phi.contains_phi or phi.confidence >= config.PHI_THRESHOLD else "cloud"
        )
        job_store.save(job)

    local_pages = [p for p in job["pages"] if p["route"] == "local"]
    cloud_pages = [p for p in job["pages"] if p["route"] == "cloud"]

    # 2. one Gemini call for ALL cloud pages, concurrent with the local sequence
    executor = ThreadPoolExecutor(max_workers=1)
    cloud_future = None
    if cloud_pages:
        cloud_paths = [_page_path(p) for p in cloud_pages]
        for page in cloud_pages:
            page["state"] = PageState.EXTRACTING.value
        job_store.save(job)
        cloud_future = executor.submit(tools.extract_cloud, job_id, cloud_paths)

    # 3. local extraction of PHI pages, sequential; the page is held in
    #    data/local/ regardless of whether its extraction succeeds
    local_datas = []
    for page in local_pages:
        page["state"] = PageState.EXTRACTING.value
        job_store.save(job)
        result = tools.extract_local(job_id, page["page_id"], _page_path(page))
        page["extraction_retries"] = result.retries
        if result.data is not None:
            local_datas.append(result.data)
            page["state"] = PageState.DONE.value
        else:
            page["state"] = PageState.FAILED.value
            page["error"] = result.error
        _move(_page_path(page), LOCAL_DIR)
        job_store.save(job)

    # 4. join the cloud call
    cloud_data = None
    if cloud_future is not None:
        result = cloud_future.result()
        cloud_data = result.data
        for page in cloud_pages:
            page["extraction_retries"] = result.retries
            if result.data is not None:
                page["state"] = PageState.DONE.value
                _move(_page_path(page), CLOUD_DIR)
            else:
                # failed cloud pages stay in uploads/ for a manual re-run
                page["state"] = PageState.FAILED.value
                page["error"] = result.error
        job_store.save(job)
    executor.shutdown(wait=False)

    # 5. merge both tracks into the single job result
    merged, conflicts, local_union = merge_results(local_datas, cloud_data)
    job["local_data"] = local_union
    job["cloud_data"] = cloud_data
    job["extracted_data"] = merged
    job["conflicts"] = conflicts
    job["one_liner"] = excel_column_map.build_one_liner(merged) if merged else None

    failed_pages = [p for p in job["pages"] if p["state"] == PageState.FAILED.value]
    if failed_pages:
        job["error"] = f"{len(failed_pages)}/{len(job['pages'])} strán zlyhalo"
    job["state"] = (
        JobState.DONE.value
        if any(p["state"] == PageState.DONE.value for p in job["pages"])
        else JobState.FAILED.value
    )
    job["finished"] = job_store.now_iso()
    job_store.save(job)


def merge_results(local_datas: list[dict], cloud_data: dict | None):
    """Field-level merge over the column map: non-null union of the local page
    results (in page order) and the cloud result. On a real conflict the local
    value wins for patient identity, the cloud value everywhere else, and the
    conflict is recorded for the UI."""
    local_union = _union(local_datas)
    if local_union is None and cloud_data is None:
        return None, [], None

    merged: dict = {}
    conflicts = []
    for path, _label in excel_column_map.COLUMNS:
        local_value = excel_column_map.get_value(local_union, path) if local_union else None
        cloud_value = excel_column_map.get_value(cloud_data, path) if cloud_data else None
        if local_value is not None and cloud_value is not None and local_value != cloud_value:
            winner = local_value if path.startswith("patient.") else cloud_value
            conflicts.append({"field": path, "local": local_value, "cloud": cloud_value})
        else:
            winner = local_value if local_value is not None else cloud_value
        _set_value(merged, path, winner)

    # The birth number encodes the birth date exactly — prefer it over
    # whatever age the vision model read (or guessed) off the scan.
    birth_number = excel_column_map.get_value(merged, "patient.birth_number")
    derived_age = age_from_birth_number(birth_number, _reference_date(merged))
    if derived_age is not None:
        _set_value(merged, "patient.age", derived_age)

    return merged, conflicts, local_union


def _reference_date(merged: dict) -> date | None:
    """Age as of the procedure date if we have one, otherwise today."""
    raw = excel_column_map.get_value(merged, "procedure.date")
    if raw:
        try:
            return date.fromisoformat(str(raw)[:10])
        except ValueError:
            pass
    return None


def _union(datas: list[dict]) -> dict | None:
    """First non-null value per field across the local pages, in page order."""
    if not datas:
        return None
    union: dict = {}
    for path, _label in excel_column_map.COLUMNS:
        value = None
        for data in datas:
            value = excel_column_map.get_value(data, path)
            if value is not None:
                break
        _set_value(union, path, value)
    return union


def _set_value(data: dict, dotted_path: str, value) -> None:
    keys = dotted_path.split(".")
    node = data
    for key in keys[:-1]:
        node = node.setdefault(key, {})
    node[keys[-1]] = value


def _page_path(page: dict) -> Path:
    path = find_page_image(page["page_id"], page["ext"])
    if path is None:
        raise FileNotFoundError(f"image for page {page['page_id']} not found")
    return path


def _move(image_path: Path, target_dir: Path) -> None:
    if image_path.parent != target_dir:
        shutil.move(str(image_path), str(target_dir / image_path.name))
