import uuid
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, url_for

from agent.orchestrator import process_document
from schemas import excel_column_map
from storage import jsonl_store
from storage.paths import RESULTS_PATH, UPLOADS_DIR, ensure_dirs

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
app.secret_key = "colono-extract-mvp"  # only protects flash messages, no sessions
ensure_dirs()


@app.get("/")
def index():
    recent = list(reversed(jsonl_store.read_all(RESULTS_PATH)))[:20]
    return render_template("upload.html", recent=recent)


@app.post("/upload")
def upload():
    file = request.files.get("document")
    if file is None or not file.filename:
        flash("Vyber súbor so skenom.")
        return redirect(url_for("index"))
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        flash(f"Nepodporovaný formát „{ext}“ — podporované: {', '.join(sorted(ALLOWED_EXTENSIONS))}.")
        return redirect(url_for("index"))

    doc_id = uuid.uuid4().hex
    image_path = UPLOADS_DIR / f"{doc_id}{ext}"
    file.save(image_path)
    process_document(doc_id, image_path, file.filename)
    return redirect(url_for("result", doc_id=doc_id))


@app.get("/result/<doc_id>")
def result(doc_id):
    record = jsonl_store.find_by(RESULTS_PATH, "doc_id", doc_id)
    if record is None:
        abort(404)
    extracted = record.get("extracted_data")
    tsv_line = excel_column_map.to_tsv_line(extracted) if extracted else None
    return render_template(
        "result.html",
        r=record,
        tsv_line=tsv_line,
        sections=_sections(extracted),
    )


def _sections(extracted):
    """Group extracted values by schema section, in column-map order, for display."""
    if not extracted:
        return []
    grouped: dict[str, list] = {}
    for path, label in excel_column_map.COLUMNS:
        section = path.split(".")[0]
        grouped.setdefault(section, []).append((label, excel_column_map.get_value(extracted, path)))
    return list(grouped.items())


if __name__ == "__main__":
    app.run(debug=True, port=5000)
