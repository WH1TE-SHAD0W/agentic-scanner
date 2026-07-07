# Colono-Extract

Agentic MVP pipeline for scanned Slovak colonoscopy-screening forms:

1. **Upload** an image through the web UI.
2. A **local** LM Studio vision model screens the scan for PHI (meno, rodné číslo, adresa, …).
3. **Routing** (fail-safe): PHI-flagged or uncertain documents are held in `data/local/` and
   never leave the machine. Only confidently clean scans go to the cloud track.
4. **Gemini** extracts structured data against `schemas/extraction_schema.json`
   (structured output + local JSON-schema validation with a bounded retry loop).
5. The result page shows the extracted data, a deterministic one-liner summary, and a
   **copy-pasteable TSV row** in the exact column order of the registry spreadsheet.

## Architecture

```
app.py                      Flask entrypoint + routes
config.py                   env-driven settings
agent/
  orchestrator.py           DocState machine: UPLOADED → CLASSIFYING → {LOCAL_HELD | EXTRACTING} → {DONE | FAILED}
  tools.py                  trace-logged tool wrappers (fail-closed PHI policy lives here)
  phi_classifier.py         LM Studio call + robust JSON parsing
  extractor.py              Gemini structured extraction + validation + bounded retry
schemas/
  extraction_schema.json    Gemini response_schema (nullable style)
  schema_loader.py          nullable → standard JSON Schema conversion + validate()
  excel_column_map.py       ordered field→column map, to_tsv_line(), build_one_liner()
storage/
  jsonl_store.py            append/read for JSONL files
  paths.py                  data/log directory conventions
data/results.jsonl          source of truth — one record per document
logs/run.jsonl              agent trace — one record per tool call/attempt (the "why")
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
  the document is treated as PHI and held locally.
- Images move by decision: `data/local/` (held, never sent), `data/cloud/` (extracted),
  failed extractions stay in `data/uploads/` for a manual re-run.
- `data/` and `logs/` are gitignored — patient scans and results never enter git.

## Rebuilding the CSS

`web/static/tailwind.css` is compiled with the Tailwind standalone CLI and committed:

```powershell
.tools\tailwindcss.exe -i web\static\input.css -o web\static\tailwind.css --minify
```
