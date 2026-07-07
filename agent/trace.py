from datetime import datetime, timezone

from storage import jsonl_store
from storage.paths import RUN_LOG_PATH


def log_trace(
    doc_id: str,
    step: str,
    tool: str,
    latency_ms: int,
    success: bool,
    input_tokens: int = 0,
    output_tokens: int = 0,
    error: str | None = None,
) -> None:
    jsonl_store.append(
        RUN_LOG_PATH,
        {
            "doc_id": doc_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "step": step,
            "tool": tool,
            "latency_ms": latency_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "success": success,
            "error": error,
        },
    )
