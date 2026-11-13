FROM python:3.12-slim

# Render passes its service variables as build args, and its 512MB free
# instance runs with vector retrieval off (render.yaml), so there the
# embedder download and the 9,823-chunk index build are skipped. Hugging
# Face (16GB) keeps the default and builds both.
ARG ENABLE_VECTOR_RETRIEVAL=true

# Hugging Face Spaces runs containers as UID 1000; building as that same
# user keeps the corpus, vector index and model cache writable at runtime.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/vakeel \
    PATH=/home/vakeel/.local/bin:$PATH \
    HF_HOME=/home/vakeel/.cache/huggingface \
    USE_GPU=false \
    ENABLE_VECTOR_RETRIEVAL=${ENABLE_VECTOR_RETRIEVAL} \
    ENABLE_CROSS_ENCODER=false

RUN useradd --create-home --uid 1000 vakeel \
    && mkdir /app && chown vakeel:vakeel /app
USER vakeel
WORKDIR /app

# CPU-only torch first: the default wheel bundles ~2GB of CUDA libraries
# that no free CPU host can use.
COPY --chown=vakeel:vakeel requirements.txt ./requirements.txt
RUN pip install --user --upgrade pip \
    && pip install --user torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --user -r requirements.txt

# The embedder loads with local_files_only, so it must be baked into the
# image rather than fetched on the first query.
RUN if [ "$ENABLE_VECTOR_RETRIEVAL" != "false" ]; then \
        python -c "from huggingface_hub import snapshot_download; snapshot_download('BAAI/bge-small-en-v1.5')"; \
    fi

# Bundled India Code PDFs: the corpus build reads these rather than
# downloading from indiacode.gov.in, which now refuses the build's client.
COPY --chown=vakeel:vakeel statutes ./statutes
COPY --chown=vakeel:vakeel app ./app
RUN python -m app.ingest.prepare_product_corpus \
    && if [ "$ENABLE_VECTOR_RETRIEVAL" != "false" ]; then python -m app.retrieval.build_product_index; fi

# Set only now: CLOUD mode refuses to start without CORS_ORIGINS and
# TRUSTED_HOSTS, which the build steps above don't need. A deployed image
# then can't fall back to LOCAL (open API docs, provider errors shown) just
# because the platform variable was forgotten.
ENV DEPLOY_MODE=CLOUD

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
