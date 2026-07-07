import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path

import requests

import config

MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

PROMPT = """You are a strict privacy screen for scanned Slovak medical documents.
Look at the scan and decide whether it contains directly identifying personal data (PHI):
patient name (meno, priezvisko), birth number (rodné číslo), full date of birth,
address, phone number, e-mail, or insurance ID (číslo poistenca).
An anonymized patient code (kód pacienta) alone is NOT PHI.

Answer with ONLY this JSON object, nothing else:
{"contains_phi": true|false, "confidence": <0.0-1.0 probability that the scan contains PHI>, "reasoning": "<one short sentence>"}"""


class ClassifierError(Exception):
    pass


@dataclass
class PhiResult:
    contains_phi: bool
    confidence: float
    reasoning: str
    input_tokens: int = 0
    output_tokens: int = 0


def classify(image_path: Path) -> PhiResult:
    """Calls the local LM Studio vision model. Raises ClassifierError on any
    connection or parsing problem — the caller decides the fail-closed policy."""
    payload = {
        "temperature": 0,
        "max_tokens": 300,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": _image_to_data_uri(image_path)}},
                ],
            }
        ],
    }
    if config.LM_STUDIO_MODEL:
        payload["model"] = config.LM_STUDIO_MODEL

    try:
        response = requests.post(
            f"{config.LM_STUDIO_BASE_URL}/chat/completions",
            json=payload,
            timeout=config.LM_STUDIO_TIMEOUT_S,
        )
        response.raise_for_status()
        body = response.json()
    except (requests.RequestException, ValueError) as e:
        raise ClassifierError(f"LM Studio request failed: {e}") from e

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ClassifierError(f"unexpected LM Studio response shape: {body}") from e

    parsed = _parse_json(content)
    try:
        confidence = float(parsed["confidence"])
    except (KeyError, TypeError, ValueError) as e:
        raise ClassifierError(f"classifier JSON missing usable confidence: {parsed}") from e

    usage = body.get("usage") or {}
    return PhiResult(
        contains_phi=bool(parsed.get("contains_phi", True)),
        confidence=max(0.0, min(1.0, confidence)),
        reasoning=str(parsed.get("reasoning", "")),
        input_tokens=usage.get("prompt_tokens", 0),
        output_tokens=usage.get("completion_tokens", 0),
    )


def _image_to_data_uri(image_path: Path) -> str:
    path = Path(image_path)
    mime = MIME_TYPES.get(path.suffix.lower(), "image/jpeg")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _parse_json(content: str) -> dict:
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        raise ClassifierError(f"no JSON in classifier response: {content[:200]!r}")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise ClassifierError(f"unparseable classifier JSON: {e}") from e
