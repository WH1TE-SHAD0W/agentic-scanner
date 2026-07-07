"""Structured extraction of PHI-flagged pages by the local LM Studio model —
the same schema and retry contract as the cloud extractor, but nothing leaves disk."""

import json
import time
from pathlib import Path

import requests

import config
from agent.extractor import EXTRACTION_PROMPT, ExtractionResult
from agent.phi_classifier import _image_to_data_uri, _parse_json, ClassifierError
from schemas import schema_loader


def extract_document(image_path: Path, on_attempt) -> ExtractionResult:
    """Bounded-retry structured extraction of ONE page via LM Studio.

    Same `on_attempt` trace contract as the cloud extractor. Tries constrained
    decoding (response_format json_schema) first; if the server rejects it,
    falls back to prompt-only JSON within the same attempt.
    """
    validation_schema = schema_loader.load_validation_schema()
    data_uri = _image_to_data_uri(image_path)

    prompt = EXTRACTION_PROMPT
    use_response_format = True
    last_error = None
    for attempt in range(1 + config.MAX_EXTRACTION_RETRIES):
        started = time.monotonic()
        try:
            body = _call_lm_studio(prompt, data_uri, validation_schema if use_response_format else None)
        except _UnsupportedResponseFormat:
            # server rejected constrained decoding — retry this attempt without it
            use_response_format = False
            try:
                body = _call_lm_studio(prompt, data_uri, None)
            except ClassifierError as e:
                last_error = str(e)
                on_attempt("extract", _ms(started), 0, 0, False, str(e))
                continue
        except ClassifierError as e:
            last_error = str(e)
            on_attempt("extract", _ms(started), 0, 0, False, str(e))
            continue

        try:
            content = body["choices"][0]["message"]["content"]
            data = _parse_json(content)
        except (KeyError, IndexError, TypeError, ClassifierError) as e:
            last_error = f"unparseable local extraction: {e}"
            on_attempt("extract", _ms(started), 0, 0, False, last_error)
            continue

        usage = body.get("usage") or {}
        on_attempt(
            "extract",
            _ms(started),
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
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


class _UnsupportedResponseFormat(Exception):
    pass


def _call_lm_studio(prompt: str, data_uri: str, response_schema: dict | None) -> dict:
    payload = {
        "temperature": 0,
        "max_tokens": 4000,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }
        ],
    }
    if config.LM_STUDIO_MODEL:
        payload["model"] = config.LM_STUDIO_MODEL
    if response_schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "extraction", "schema": response_schema},
        }

    try:
        response = requests.post(
            f"{config.LM_STUDIO_BASE_URL}/chat/completions",
            json=payload,
            timeout=config.LM_STUDIO_EXTRACT_TIMEOUT_S,
        )
        if response.status_code == 400 and response_schema is not None:
            raise _UnsupportedResponseFormat(response.text[:200])
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as e:
        raise ClassifierError(f"LM Studio request failed: {e}") from e


def _ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)
