FROM python:3.11-slim

WORKDIR /app

# System deps kept minimal; curl only for local debugging of the healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# CPU-only torch wheel keeps the image small (~1-2GB instead of ~6GB with CUDA).
# To target a GPU node, drop the --index-url line and pin a CUDA-enabled torch build.
RUN pip install --no-cache-dir -r requirements.txt \
    --extra-index-url https://download.pytorch.org/whl/cpu

COPY main.py .

ENV USE_STUB=1 \
    MODEL_NAME=distilbert-base-uncased-finetuned-sst-2-english \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
