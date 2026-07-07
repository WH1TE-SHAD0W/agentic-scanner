"""Offline smoke checks — no LM Studio or Gemini needed.

Run:  .venv\\Scripts\\python tests\\offline_checks.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import extractor, orchestrator
from schemas import excel_column_map, schema_loader
from storage import job_store
from storage.paths import JOBS_DIR, UPLOADS_DIR, ensure_dirs


def build_valid_payload():
    def build(node):
        if node.get("type") == "object":
            return {k: build(v) for k, v in node["properties"].items()}
        return None

    return build(schema_loader.load_gemini_schema())


def test_merge_policy():
    # deliberately unparseable (invalid month) so it doesn't trigger the
    # birth-number age derivation covered separately in test_age_from_birth_number
    fake_birth_number = "999999/1234"

    local = build_valid_payload()
    local["patient"]["age"] = 67
    local["patient"]["birth_number"] = fake_birth_number
    local["findings"]["nalez"] = 1

    cloud = build_valid_payload()
    cloud["patient"]["age"] = 70          # conflict -> local wins (patient.*)
    cloud["findings"]["nalez"] = 2        # conflict -> cloud wins (clinical)
    cloud["findings"]["polyp_count"] = 3  # only cloud -> taken

    merged, conflicts, local_union = orchestrator.merge_results([local], cloud)
    assert merged["patient"]["age"] == 67
    assert merged["patient"]["birth_number"] == fake_birth_number
    assert merged["findings"]["nalez"] == 2
    assert merged["findings"]["polyp_count"] == 3
    assert {c["field"] for c in conflicts} == {"patient.age", "findings.nalez"}
    assert local_union["patient"]["age"] == 67

    # union across local pages: first non-null in page order
    page2 = build_valid_payload()
    page2["patient"]["sex"] = "M"
    merged2, _, union2 = orchestrator.merge_results([local, page2], None)
    assert union2["patient"]["sex"] == "M" and union2["patient"]["age"] == 67
    assert merged2["patient"]["sex"] == "M"

    assert orchestrator.merge_results([], None) == (None, [], None)
    print("merge policy OK")


class FakeUpload:
    def __init__(self, filename):
        self.filename = filename

    def save(self, path):
        Path(path).write_bytes(b"fake")


def test_job_store_roundtrip():
    ensure_dirs()
    job = job_store.create_job()
    job_store.add_page(job, FakeUpload("scan strana 1.png"))
    job_store.add_page(job, FakeUpload("scan strana 2.jpg"))
    job_store.save(job)

    loaded = job_store.load(job["job_id"])
    assert loaded == job
    assert len(loaded["pages"]) == 2
    assert loaded["pages"][0]["ext"] == ".png"
    assert loaded["job_id"] in [j["job_id"] for j in job_store.list_jobs()]

    # cleanup the artifacts this test created
    (JOBS_DIR / f"{job['job_id']}.json").unlink()
    for page in job["pages"]:
        (UPLOADS_DIR / f"{page['page_id']}{page['ext']}").unlink()
    print("job store round-trip OK")


def test_multi_image_extraction():
    captured = {}

    class FakeResp:
        def __init__(self, text):
            self.text = text
            self.usage_metadata = None

    class FakeModels:
        def generate_content(self, **kw):
            captured["contents"] = kw["contents"]
            assert kw["config"].response_schema is not None
            return FakeResp(json.dumps(build_valid_payload()))

    class FakeClient:
        def __init__(self, **kw):
            self.models = FakeModels()

    ensure_dirs()
    img1 = UPLOADS_DIR / "_test_a.png"
    img2 = UPLOADS_DIR / "_test_b.png"
    img1.write_bytes(b"a")
    img2.write_bytes(b"b")

    original = extractor.genai.Client
    extractor.genai.Client = FakeClient
    try:
        result = extractor.extract_document([img1, img2], lambda *a: None)
    finally:
        extractor.genai.Client = original
        img1.unlink()
        img2.unlink()

    assert result.data is not None and result.error is None
    contents = captured["contents"]
    assert len(contents) == 3, "expected 2 image parts + 1 prompt"
    assert isinstance(contents[-1], str), "prompt must come last"
    print("multi-image extraction OK")


def test_age_from_birth_number():
    from datetime import date

    from schemas.birth_number import age_from_birth_number, parse_birth_date

    assert parse_birth_date("6704212086") == date(1967, 4, 21)
    assert parse_birth_date("6754212086") == date(1967, 4, 21)  # women: month + 50
    assert age_from_birth_number("6704212086", date(2026, 7, 7)) == 59
    assert age_from_birth_number("6704212086", date(2026, 3, 1)) == 58  # birthday not yet reached
    assert parse_birth_date("") is None and parse_birth_date("abc") is None

    local = build_valid_payload()
    local["patient"]["birth_number"] = "6704212086"
    local["patient"]["age"] = 40  # wrong vision guess -> must be overridden by the merge
    local["procedure"]["date"] = "2026-07-07"
    merged, _, _ = orchestrator.merge_results([local], None)
    assert merged["patient"]["age"] == 59, merged["patient"]["age"]
    print("age-from-birth-number OK")


def test_tsv_shape():
    merged = build_valid_payload()
    line = excel_column_map.to_tsv_line(merged)
    assert line.count("\t") == len(excel_column_map.COLUMNS) - 1
    print("TSV shape OK")


if __name__ == "__main__":
    import app  # noqa: F401  — import check for the whole wiring

    test_merge_policy()
    test_job_store_roundtrip()
    test_multi_image_extraction()
    test_age_from_birth_number()
    test_tsv_shape()
    print("ALL OFFLINE CHECKS PASSED")
