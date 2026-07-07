import shutil
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

import config
from agent import tools
from schemas import excel_column_map
from storage import jsonl_store
from storage.paths import CLOUD_DIR, LOCAL_DIR, RESULTS_PATH


class DocState(str, Enum):
    UPLOADED = "UPLOADED"
    CLASSIFYING = "CLASSIFYING"
    LOCAL_HELD = "LOCAL_HELD"
    EXTRACTING = "EXTRACTING"
    DONE = "DONE"
    FAILED = "FAILED"


def process_document(doc_id: str, image_path: Path, filename: str) -> dict:
    """Runs one document through the state machine:

        UPLOADED -> CLASSIFYING -> { LOCAL_HELD | EXTRACTING } -> { DONE | FAILED }

    Appends the result record to results.jsonl and returns it."""
    state = DocState.CLASSIFYING
    phi = tools.phi_classify(doc_id, image_path)

    record = {
        "doc_id": doc_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "filename": filename,
        "route": None,
        "state": None,
        "phi_confidence": phi.confidence,
        "phi_reasoning": phi.reasoning,
        "extraction_status": "not_attempted",
        "extraction_retries": 0,
        "extracted_data": None,
        "one_liner": None,
        "error": None,
    }

    if phi.contains_phi or phi.confidence >= config.PHI_THRESHOLD:
        record["route"] = "local"
        _move(image_path, LOCAL_DIR)
        state = DocState.LOCAL_HELD
    else:
        record["route"] = "cloud"
        state = DocState.EXTRACTING
        extraction = tools.extract(doc_id, image_path)
        record["extraction_retries"] = extraction.retries
        if extraction.data is not None:
            record["extraction_status"] = "ok"
            record["extracted_data"] = extraction.data
            record["one_liner"] = excel_column_map.build_one_liner(extraction.data)
            _move(image_path, CLOUD_DIR)
            state = DocState.DONE
        else:
            # image stays in uploads/ for a manual re-run
            record["extraction_status"] = "failed"
            record["error"] = extraction.error
            state = DocState.FAILED

    record["state"] = state.value
    jsonl_store.append(RESULTS_PATH, record)
    return record


def _move(image_path: Path, target_dir: Path) -> None:
    shutil.move(str(image_path), str(target_dir / Path(image_path).name))
