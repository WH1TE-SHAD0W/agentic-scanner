import copy
import json
from pathlib import Path

import jsonschema

SCHEMA_PATH = Path(__file__).resolve().parent / "extraction_schema.json"

_validation_schema = None


def load_gemini_schema() -> dict:
    """Raw schema in Gemini response_schema format (uses `nullable`)."""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def load_validation_schema() -> dict:
    """Standard JSON Schema for local validation: `nullable: true` -> type [t, "null"]."""
    return _convert(copy.deepcopy(load_gemini_schema()))


def validate(data: dict) -> str | None:
    """Returns None when valid, otherwise a short validation error message."""
    global _validation_schema
    if _validation_schema is None:
        _validation_schema = load_validation_schema()
    try:
        jsonschema.validate(data, _validation_schema)
        return None
    except jsonschema.ValidationError as e:
        path = "/".join(str(p) for p in e.absolute_path) or "(root)"
        return f"{path}: {e.message}"


def _convert(node):
    if isinstance(node, dict):
        if node.pop("nullable", False) and "type" in node:
            node["type"] = [node["type"], "null"]
        for child in node.values():
            _convert(child)
    elif isinstance(node, list):
        for child in node:
            _convert(child)
    return node
