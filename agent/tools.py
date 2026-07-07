"""The tool functions the orchestrator calls — the single place external
model calls are timed, trace-logged, and given their failure policy."""

import time
from pathlib import Path

from agent import extractor, local_extractor, phi_classifier, trace
from agent.phi_classifier import ClassifierError, PhiResult


def phi_classify(job_id: str, page_id: str, image_path: Path) -> PhiResult:
    """Local PHI screen. Fails CLOSED: any error counts as PHI with full
    confidence, so the scan never leaves disk on a broken classifier."""
    started = time.monotonic()
    try:
        result = phi_classifier.classify(image_path)
    except ClassifierError as e:
        trace.log_trace(job_id, page_id, "phi_classify", "lm_studio", _ms(started), success=False, error=str(e))
        return PhiResult(contains_phi=True, confidence=1.0, reasoning=f"fail-closed: {e}")
    trace.log_trace(
        job_id,
        page_id,
        "phi_classify",
        "lm_studio",
        _ms(started),
        success=True,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
    return result


def extract_cloud(job_id: str, image_paths: list[Path]) -> extractor.ExtractionResult:
    """One Gemini call covering all cloud-cleared pages of the job (page_id None in the trace)."""
    return extractor.extract_document(image_paths, _attempt_logger(job_id, None, "gemini"))


def extract_local(job_id: str, page_id: str, image_path: Path) -> extractor.ExtractionResult:
    return local_extractor.extract_document(image_path, _attempt_logger(job_id, page_id, "lm_studio"))


def _attempt_logger(job_id: str, page_id: str | None, tool: str):
    def on_attempt(step, latency_ms, input_tokens, output_tokens, success, error):
        trace.log_trace(
            job_id,
            page_id,
            step,
            tool,
            latency_ms,
            success=success,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            error=error,
        )

    return on_attempt


def _ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)
