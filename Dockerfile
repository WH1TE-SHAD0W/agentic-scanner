# syntax=docker/dockerfile:1

# ---- builder: build the venv, nothing else ships from this stage ----
FROM python:3.12-slim AS builder

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- final: runtime image ----
FROM python:3.12-slim

RUN addgroup --system --gid 568 app && \
    adduser --system --uid 568 --ingroup app app

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

COPY . .

# /app/data and /app/logs are meant to be mounted volumes (see docker-compose.yml);
# create them here too so the image is self-contained without a compose file.
RUN mkdir -p /app/data /app/logs && chown -R app:app /app

USER app
EXPOSE 5000

# workers=1 is deliberate: job processing runs in a background thread inside
# the worker that received the "start" request, and later polling requests
# for that job must land in the same process — see agent/orchestrator.py.
# Never add --max-requests here, it would recycle the worker mid-job.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", \
     "--worker-class", "gthread", "--threads", "4", \
     "--timeout", "120", "app:app"]
