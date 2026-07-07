import json
from pathlib import Path


def append(path: Path, record: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_all(path: Path) -> list[dict]:
    if not Path(path).exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def find_by(path: Path, key: str, value) -> dict | None:
    for record in read_all(path):
        if record.get(key) == value:
            return record
    return None
