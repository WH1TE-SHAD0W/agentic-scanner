import json
import time
from dataclasses import dataclass
from pathlib import Path

from google import genai
from google.genai import types

import config
from agent.phi_classifier import MIME_TYPES
from schemas import schema_loader

EXTRACTION_PROMPT = """Extract the structured data from this scanned Slovak colonoscopy
screening form. The images are pages/sections of ONE form for ONE patient — combine them
into a single record. Fill every field of the schema; use null where a value is missing or
unreadable — never guess. Dates as YYYY-MM-DD. For checkbox/yes-no fields use
1 = yes/checked, 0 = no/unchecked, null = unknown."""


@dataclass
class ExtractionResult:
    data: dict | None
    retries: int  # re-attempts actually used (0 = succeeded first try)
    error: str | None


def extract_document(image_paths: list[Path], on_attempt) -> ExtractionResult:
    """Gemini structured extraction over all pages in one call, with a bounded
    retry loop.

    `on_attempt(step, latency_ms, input_tokens, output_tokens, success, error)`
    is invoked for every Gemini call and every validation, so the run trace
    records each attempt, not just the outcome.
    """
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    image_parts = [
        types.Part.from_bytes(
            data=Path(p).read_bytes(),
            mime_type=MIME_TYPES.get(Path(p).suffix.lower(), "image/jpeg"),
        )
        for p in image_paths
    ]
    schema = schema_loader.load_gemini_schema()

    prompt = EXTRACTION_PROMPT
    last_error = None
    for attempt in range(1 + config.MAX_EXTRACTION_RETRIES):
        started = time.monotonic()
        try:
            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=[*image_parts, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0,
                ),
            )
            data = json.loads(response.text)
        except Exception as e:  # network, API, blocked response, bad JSON
            last_error = f"Gemini call failed: {e}"
            on_attempt("extract", _ms(started), 0, 0, False, str(e))
            continue

        usage = response.usage_metadata
        on_attempt(
            "extract",
            _ms(started),
            (usage.prompt_token_count or 0) if usage else 0,
            (usage.candidates_token_count or 0) if usage else 0,
            True,
            None,
        )

        validation_error = schema_loader.validate(data)
        on_attempt("validate", 0, 0, 0, validation_error is None, validation_error)
        if validation_error is None:
            return ExtractionResult(data=data, retries=attempt, error=None)

        last_error = f"schema validation failed: {validation_error}"
        prompt = (
            EXTRACTION_PROMPT
            + f"\n\nYour previous answer failed schema validation: {validation_error}."
            + " Return corrected JSON that satisfies the schema."
        )

    return ExtractionResult(data=None, retries=config.MAX_EXTRACTION_RETRIES, error=last_error)


def _ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)
