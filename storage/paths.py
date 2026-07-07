from config import BASE_DIR

DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"  # incoming images, pre-routing
LOCAL_DIR = DATA_DIR / "local"      # PHI-flagged, never leaves disk
CLOUD_DIR = DATA_DIR / "cloud"      # extracted via the cloud track
JOBS_DIR = DATA_DIR / "jobs"        # one mutable JSON file per job

LOGS_DIR = BASE_DIR / "logs"
RUN_LOG_PATH = LOGS_DIR / "run.jsonl"


def ensure_dirs():
    for directory in (UPLOADS_DIR, LOCAL_DIR, CLOUD_DIR, JOBS_DIR, LOGS_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def find_page_image(page_id: str, ext: str):
    """A page image lives in uploads/ before routing, then local/ or cloud/."""
    for directory in (UPLOADS_DIR, LOCAL_DIR, CLOUD_DIR):
        path = directory / f"{page_id}{ext}"
        if path.exists():
            return path
    return None
