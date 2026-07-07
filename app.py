from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, send_file, url_for

from agent import orchestrator
from schemas import excel_column_map
from storage import job_store
from storage.paths import ensure_dirs, find_page_image

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
app.secret_key = "colono-extract-mvp"  # only protects flash messages, no sessions
ensure_dirs()


@app.get("/")
def index():
    return render_template("index.html", jobs=job_store.list_jobs())


@app.post("/jobs")
def create_job():
    files = _valid_files()
    if files is None:
        return redirect(url_for("index"))
    job = job_store.create_job()
    for f in files:
        job_store.add_page(job, f)
    job_store.save(job)
    return redirect(url_for("job_detail", job_id=job["job_id"]))


@app.post("/jobs/<job_id>/pages")
def add_pages(job_id):
    job = _load_or_404(job_id)
    if job["state"] != "OPEN":
        flash("Stránky sa dajú pridať iba do otvoreného jobu.")
        return redirect(url_for("job_detail", job_id=job_id))
    files = _valid_files()
    if files is not None:
        for f in files:
            job_store.add_page(job, f)
        job_store.save(job)
    return redirect(url_for("job_detail", job_id=job_id))


@app.post("/jobs/<job_id>/start")
def start_job(job_id):
    job = _load_or_404(job_id)
    if job["state"] != "OPEN":
        flash("Job už bol spustený.")
    elif not job["pages"]:
        flash("Job nemá žiadne stránky.")
    else:
        orchestrator.start_job(job)
    return redirect(url_for("job_detail", job_id=job_id))


@app.get("/jobs/<job_id>")
def job_detail(job_id):
    job = _load_or_404(job_id)
    extracted = job.get("extracted_data")
    return render_template(
        "job.html",
        job=job,
        tsv_line=excel_column_map.to_tsv_line(extracted) if extracted else None,
        sections=_sections(extracted),
    )


@app.get("/pages/<page_id>/image")
def page_image(page_id):
    for ext in ALLOWED_EXTENSIONS:
        path = find_page_image(page_id, ext)
        if path is not None:
            return send_file(path)
    abort(404)


def _load_or_404(job_id: str) -> dict:
    job = job_store.load(job_id)
    if job is None:
        abort(404)
    return job


def _valid_files():
    files = [f for f in request.files.getlist("documents") if f and f.filename]
    if not files:
        flash("Vyber aspoň jeden sken.")
        return None
    bad = [f.filename for f in files if Path(f.filename).suffix.lower() not in ALLOWED_EXTENSIONS]
    if bad:
        flash(
            f"Nepodporovaný formát: {', '.join(bad)} — podporované: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
        )
        return None
    return files


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
    # no reloader — it would kill running job threads on a code change
    app.run(debug=True, port=5000, use_reloader=False)
