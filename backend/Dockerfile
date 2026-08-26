FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    USE_GPU=false \
    ENABLE_VECTOR_RETRIEVAL=false \
    ENABLE_CROSS_ENCODER=false

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app
RUN python -m app.ingest.prepare_product_corpus

RUN useradd --create-home --uid 10001 vakeel \
    && chown -R vakeel:vakeel /app
USER vakeel

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
