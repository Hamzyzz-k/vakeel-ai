FROM python:3.12-slim

# Hugging Face Spaces runs containers as UID 1000; building as that same
# user keeps the corpus, vector index and model cache writable at runtime.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/vakeel \
    PATH=/home/vakeel/.local/bin:$PATH \
    HF_HOME=/home/vakeel/.cache/huggingface \
    USE_GPU=false \
    ENABLE_VECTOR_RETRIEVAL=true \
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
RUN python -c "from huggingface_hub import snapshot_download; snapshot_download('BAAI/bge-small-en-v1.5')"

COPY --chown=vakeel:vakeel app ./app
RUN python -m app.ingest.prepare_product_corpus \
    && python -m app.retrieval.build_product_index

# Set only now: CLOUD mode refuses to start without CORS_ORIGINS and
# TRUSTED_HOSTS, which the build steps above don't need. A deployed image
# then can't fall back to LOCAL (open API docs, provider errors shown) just
# because the platform variable was forgotten.
ENV DEPLOY_MODE=CLOUD

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
