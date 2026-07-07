from config import BASE_DIR

DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"  # incoming images, pre-routing
LOCAL_DIR = DATA_DIR / "local"      # PHI-flagged, never leaves disk
CLOUD_DIR = DATA_DIR / "cloud"      # extracted via the cloud track
RESULTS_PATH = DATA_DIR / "results.jsonl"

LOGS_DIR = BASE_DIR / "logs"
RUN_LOG_PATH = LOGS_DIR / "run.jsonl"


def ensure_dirs():
    for directory in (UPLOADS_DIR, LOCAL_DIR, CLOUD_DIR, LOGS_DIR):
        directory.mkdir(parents=True, exist_ok=True)
