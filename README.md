# Colono-Extract

Agentic pipeline for scanned Slovak colonoscopy-screening forms, organized as **jobs**:
one job = one form (one extraction), even when it spans several scanned pages.

1. **Create a job** with one or more page images, then press **Start** — the job runs in a
   background thread and the job page auto-refreshes with per-page progress.
2. Each page is screened for PHI by a **local** LM Studio vision model (meno, rodné číslo,
   adresa, …), sequentially.
3. **Routing** (fail-safe): PHI-flagged or uncertain pages are held in `data/local/` and
   never leave the machine — they are extracted **locally** by the same LM Studio model.
   Confidently clean pages go **together in one Gemini call** (concurrent with the local work).
4. Both tracks validate against `schemas/extraction_schema.json` with a bounded retry loop,
   then **merge field-by-field** into one record: on a conflict, the local value wins for
   patient identity, the cloud value for clinical fields, and the conflict is shown in the UI.
5. The job page shows the merged data, per-page details (thumbnail, route, confidence,
   reasoning, errors), a deterministic one-liner summary, and a **copy-pasteable TSV row**
   in the exact column order of the registry spreadsheet.

## Architecture

```
app.py                      Flask entrypoint + job routes
config.py                   env-driven settings
agent/
  orchestrator.py           job state machine: OPEN → RUNNING → {DONE | FAILED}; merge policy
  tools.py                  trace-logged tool wrappers (fail-closed PHI policy lives here)
  phi_classifier.py         LM Studio PHI screen + robust JSON parsing
  local_extractor.py        LM Studio structured extraction for PHI pages (never leaves disk)
  extractor.py              Gemini structured extraction, all cloud pages in one call
schemas/
  extraction_schema.json    Gemini response_schema (nullable style)
  schema_loader.py          nullable → standard JSON Schema conversion + validate()
  excel_column_map.py       ordered field→column map, to_tsv_line(), build_one_liner()
storage/
  job_store.py              one mutable JSON per job in data/jobs/ (atomic saves)
  jsonl_store.py            append/read for JSONL files
  paths.py                  data/log directory conventions
data/jobs/{job_id}.json     source of truth — one file per job, live progress + final result
logs/run.jsonl              agent trace — one record per tool call/attempt (the "why")
tests/offline_checks.py     smoke checks that need no LM Studio/Gemini
```

## Setup

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env    # fill in GEMINI_API_KEY
```

Start **LM Studio** with a vision-capable model loaded and the local server running
(default `http://localhost:1234/v1`).

## Run

```powershell
.venv\Scripts\python app.py
# → http://localhost:5000
```

## Run with Docker

```powershell
docker compose up --build
# → http://localhost:5000
```

- `Dockerfile` is multistage: a `builder` stage installs dependencies into a venv, the
  final image copies just that venv plus the app code and runs as a non-root user.
- `docker-compose.yml` mounts the host's `./data` and `./logs` as volumes (`/app/data`,
  `/app/logs` in the container) — patient scans and job state survive container
  rebuilds/restarts and stay out of the image entirely (`.dockerignore` also excludes
  `data/`, `logs/`, `.env`, so nothing sensitive ends up baked into a layer).
- Served by **gunicorn** with `--workers 1 --worker-class gthread --threads 4`. Workers=1
  is deliberate, not a placeholder: `agent/orchestrator.py` spawns a background thread per
  job when you press Start, and the job page's polling requests must land back in that
  same process to see progress. Don't add `--max-requests` or a second worker — either
  would split a job's state across processes that can't see each other's threads.
- `LM_STUDIO_BASE_URL` must point somewhere the container can actually reach — `localhost`
  means the container itself, not your host. Point it at your host's LAN/Tailscale IP
  (already the case in this repo's `.env`), or `host.docker.internal` on Docker Desktop.
- If you deploy this on native Linux (not Docker Desktop) and hit permission errors
  writing to the mounted `./data`/`./logs`, match the container's `app` user's UID/GID to
  the host directory owner, or relax the host directory permissions.

## Configuration (.env)

| Variable | Default | Meaning |
| --- | --- | --- |
| `GEMINI_API_KEY` | — | AI Studio API key (required for the cloud track) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | extraction model |
| `LM_STUDIO_BASE_URL` | `http://localhost:1234/v1` | local OpenAI-compatible endpoint |
| `LM_STUDIO_MODEL` | *(loaded model)* | model id in LM Studio |
| `PHI_THRESHOLD` | `0.2` | cloud track only when PHI confidence is **below** this |
| `MAX_EXTRACTION_RETRIES` | `2` | re-attempts after failed/invalid extraction |

## Privacy behaviour

- The PHI classifier **fails closed**: if LM Studio is unreachable or returns garbage,
  the page is treated as PHI and stays local.
- Images move by decision: `data/local/` (PHI pages — held and extracted locally, never
  sent), `data/cloud/` (extracted via Gemini), failed cloud pages stay in `data/uploads/`
  for a manual re-run.
- `data/` and `logs/` are gitignored — patient scans and results never enter git.
- Keep `GEMINI_API_KEY` only in `.env` (gitignored) — never as a default in code.

## Known caveat

The local model can hallucinate plausible values on unreadable input (schema validation
can't catch a well-formed guess). Check the per-page reasoning and the merged values on
the job page before pasting the TSV row.

## Rebuilding the CSS

`web/static/tailwind.css` is compiled with the Tailwind standalone CLI and committed:

```powershell
.tools\tailwindcss.exe -i web\static\input.css -o web\static\tailwind.css --minify
```
