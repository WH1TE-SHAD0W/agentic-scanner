import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# Local PHI classifier (LM Studio, OpenAI-compatible API)
LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "")  # empty = whatever model LM Studio has loaded
LM_STUDIO_TIMEOUT_S = int(os.getenv("LM_STUDIO_TIMEOUT_S", "120"))
LM_STUDIO_EXTRACT_TIMEOUT_S = int(os.getenv("LM_STUDIO_EXTRACT_TIMEOUT_S", "300"))

# Cloud extractor (Gemini via google-genai)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Routing is fail-safe: a document goes to the cloud track only when the PHI
# confidence is below this; anything uncertain stays local.
PHI_THRESHOLD = float(os.getenv("PHI_THRESHOLD", "0.2"))

# Re-attempts after a failed or schema-invalid extraction (total attempts = 1 + retries).
MAX_EXTRACTION_RETRIES = int(os.getenv("MAX_EXTRACTION_RETRIES", "2"))
