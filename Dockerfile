# ---- Stage 1: build the api runtime into a self-contained venv ----
FROM python:3.13-slim AS builder
WORKDIR /build
# setuptools package discovery (include = ["src*", "scripts*"]) needs the source
# tree present to build/install the project, so copy it before installing.
COPY pyproject.toml ./
COPY src ./src
COPY web ./web
# Install the project + its `api` optional-deps group into a venv we copy forward.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir ".[api]"

# ---- Stage 2: slim runtime ----
FROM python:3.13-slim AS runtime
# HF Spaces runs containers as a non-root user (uid 1000) on port 7860.
RUN useradd -m -u 1000 appuser
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    RUNS_DIR=/app/runs \
    PORT=7860
COPY src ./src
COPY web ./web
RUN mkdir -p /app/runs && chown -R appuser:appuser /app
USER appuser
EXPOSE 7860
# HF Spaces convention: listen on 0.0.0.0:7860. One worker keeps the in-memory
# rate limiter coherent; scale out via the Redis seam + more replicas if needed.
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
