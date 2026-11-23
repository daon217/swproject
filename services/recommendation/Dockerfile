FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HUB_DISABLE_TELEMETRY=1
WORKDIR /workspace
COPY services/api/requirements.lock /tmp/api-requirements.lock
RUN pip install --no-cache-dir -r /tmp/api-requirements.lock httpx==0.28.1
ARG RECO_EMBEDDER=st
ARG RECO_MODEL_NAME=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
ARG RECO_MODEL_REVISION=e8f8c211226b894fcb81acc59f3b34ba3efd5f42
COPY services/recommendation/requirements-ai.in /tmp/ai-requirements.in
RUN if [ "$RECO_EMBEDDER" = st ]; then \
      pip install --no-cache-dir torch==2.10.0 --index-url https://download.pytorch.org/whl/cpu && \
      pip install --no-cache-dir -r /tmp/ai-requirements.in; \
    elif [ "$RECO_EMBEDDER" != hash ]; then exit 1; fi
RUN useradd --uid 10001 --create-home developer
COPY services/recommendation services/recommendation
COPY services/api/kkulpick services/api/kkulpick
USER developer
# Download once at build time, pinned to the same revision used by both processes.
RUN if [ "$RECO_EMBEDDER" = st ]; then \
      python -c 'import sys; from sentence_transformers import SentenceTransformer; SentenceTransformer(sys.argv[1], revision=sys.argv[2], device="cpu", trust_remote_code=False)' "$RECO_MODEL_NAME" "$RECO_MODEL_REVISION"; fi
ENV HF_HUB_OFFLINE=1
CMD ["uvicorn", "services.recommendation.http_service:app", "--host", "0.0.0.0", "--port", "8000"]
