# samjho API — FastAPI + pgvector retrieval service.
#
# Two things this image is careful about:
#   1. The two local models (bge-small-en-v1.5, ms-marco cross-encoder) are downloaded at build
#      time, so the running container answers questions with no network access at all.
#   2. The image carries the API code and the syllabus structure only. It never carries textbook
#      text: `corpus/` is a volume the student mounts, and nothing in this image is book prose.
#      See docs/adr/ADR-001-licensing-boundary.md.
#
# Build:  docker build -f api/Dockerfile -t samjho-api .
# Run:    docker run --rm -p 8000:8000 -e DATABASE_URL=postgresql://samjho:samjho@host:5432/samjho samjho-api
# With no DATABASE_URL and no corpus, it still serves /health and /subjects — that is the
# supported pre-ingest state, not a failure.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/models \
    HF_HUB_DISABLE_TELEMETRY=1 \
    SYLLABUS_PATH=/app/data/syllabus/class10.json \
    CORPUS_DIR=/corpus

WORKDIR /app

# libgomp1 is what torch's CPU kernels link against; curl is for the healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

# Dependency layer: only the manifest + package dirs, so edits to code do not reinstall torch.
COPY pyproject.toml ./
COPY api ./api
COPY ingest ./ingest
# CPU-only torch first: the default PyPI wheel pulls ~2 GB of CUDA runtime this service never uses
# (it runs bge-small and a 6-layer cross-encoder on CPU). Measured effect: the CUDA wheels alone are
# 554 MB + 553 MB + the rest of the toolkit; the CPU wheel is ~200 MB and the image stays usable.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install --no-cache-dir .

# Model layer: bake the embeddings and the reranker into the image (no runtime download).
RUN python -m api.embed

COPY data ./data

RUN useradd --create-home --uid 10001 samjho \
    && mkdir -p /corpus \
    && chown -R samjho:samjho /app /models /corpus
USER samjho

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

# One worker: the embedding models are loaded per process and are the memory cost here.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
