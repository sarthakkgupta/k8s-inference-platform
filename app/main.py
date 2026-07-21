"""FastAPI sentiment-inference service.

Runs a small transformers sentiment model, auto-selecting CUDA when available
and falling back to CPU otherwise. Set USE_STUB=1 to skip the model download
entirely (useful for local dev, CI, and laptops with no internet/GPU).
"""
import os
import time

from fastapi import FastAPI
from fastapi.responses import Response
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

USE_STUB = os.environ.get("USE_STUB", "0") == "1"
MODEL_NAME = os.environ.get("MODEL_NAME", "distilbert-base-uncased-finetuned-sst-2-english")

app = FastAPI(title="model-inference-service")

REQUEST_COUNT = Counter(
    "predict_requests_total", "Total number of /predict requests", ["label"]
)
LATENCY_HISTOGRAM = Histogram(
    "predict_latency_seconds", "Latency of /predict requests in seconds"
)

DEVICE = "cpu"
_pipeline = None


class PredictRequest(BaseModel):
    text: str


class PredictResponse(BaseModel):
    label: str
    score: float
    latency_ms: float
    device: str


def _load_pipeline():
    """Load the model once at startup. Skipped entirely when USE_STUB=1."""
    global _pipeline, DEVICE

    if USE_STUB:
        return

    import torch
    from transformers import pipeline

    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    device_index = 0 if DEVICE == "cuda" else -1

    _pipeline = pipeline(
        "sentiment-analysis",
        model=MODEL_NAME,
        device=device_index,
    )


def _stub_predict(text: str) -> dict:
    """Deterministic fake inference: no model, no download, instant response."""
    positive_markers = ("good", "great", "love", "excellent", "amazing", "happy")
    negative_markers = ("bad", "terrible", "hate", "awful", "worst", "sad")
    lowered = text.lower()
    if any(marker in lowered for marker in negative_markers):
        return {"label": "NEGATIVE", "score": 0.99}
    if any(marker in lowered for marker in positive_markers):
        return {"label": "POSITIVE", "score": 0.99}
    return {"label": "POSITIVE", "score": 0.51}


@app.on_event("startup")
def startup():
    _load_pipeline()


@app.get("/healthz")
def healthz():
    return {"status": "ok", "stub": USE_STUB, "device": DEVICE}


@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest):
    start = time.perf_counter()

    if USE_STUB:
        result = _stub_predict(request.text)
    else:
        result = _pipeline(request.text)[0]

    elapsed_ms = (time.perf_counter() - start) * 1000

    REQUEST_COUNT.labels(label=result["label"]).inc()
    LATENCY_HISTOGRAM.observe(elapsed_ms / 1000)

    return PredictResponse(
        label=result["label"],
        score=float(result["score"]),
        latency_ms=round(elapsed_ms, 3),
        device=DEVICE,
    )


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
