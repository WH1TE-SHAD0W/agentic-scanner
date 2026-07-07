"""The tool functions the orchestrator calls — the single place external
model calls are timed, trace-logged, and given their failure policy."""

import time
from pathlib import Path

from agent import extractor, phi_classifier, trace
from agent.phi_classifier import ClassifierError, PhiResult


def phi_classify(doc_id: str, image_path: Path) -> PhiResult:
    """Local PHI screen. Fails CLOSED: any error counts as PHI with full
    confidence, so the scan never leaves disk on a broken classifier."""
    started = time.monotonic()
    try:
        result = phi_classifier.classify(image_path)
    except ClassifierError as e:
        trace.log_trace(doc_id, "phi_classify", "lm_studio", _ms(started), success=False, error=str(e))
        return PhiResult(contains_phi=True, confidence=1.0, reasoning=f"fail-closed: {e}")
    trace.log_trace(
        doc_id,
        "phi_classify",
        "lm_studio",
        _ms(started),
        success=True,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
    return result


def extract(doc_id: str, image_path: Path) -> extractor.ExtractionResult:
    def on_attempt(step, latency_ms, input_tokens, output_tokens, success, error):
        trace.log_trace(
            doc_id,
            step,
            "gemini",
            latency_ms,
            success=success,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            error=error,
        )

    return extractor.extract_document(image_path, on_attempt)


def _ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)
