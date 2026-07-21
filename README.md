# k8s-inference-platform

A minimal, real Kubernetes deployment of a model-inference service: FastAPI +
PyTorch/transformers, containerized, deployed to a local [kind](https://kind.sigs.k8s.io/)
cluster with CPU/memory-based autoscaling and Prometheus metrics. Runs entirely on a
laptop with no GPU; switching to a real GPU node is a one-line change.

## Architecture

```
                 ┌─────────────────────────────────────────────┐
                 │              kind cluster                    │
                 │                                               │
  client ──HTTP──▶  Service (ClusterIP)                          │
                 │        │                                      │
                 │        ▼                                      │
                 │  Deployment (1-6 pods, HPA on CPU)             │
                 │   ┌───────────────────────────┐                │
                 │   │ FastAPI container          │                │
                 │   │  GET  /healthz  (liveness/ │                │
                 │   │       readiness)            │                │
                 │   │  POST /predict  (sentiment  │                │
                 │   │       via transformers)     │                │
                 │   │  GET  /metrics  (Prometheus)│                │
                 │   └───────────────────────────┘                │
                 │        ▲                                      │
                 │        │ scrapes CPU usage                    │
                 │  HorizontalPodAutoscaler (metrics-server)      │
                 └─────────────────────────────────────────────┘
                        ▲
                        │ generates load
                  Locust (loadtest/)
```

Request flow: a client calls `POST /predict` with `{"text": "..."}`. The pod runs the
text through a HuggingFace sentiment pipeline (or a deterministic keyword-based stub
when `USE_STUB=1`) and returns a label, confidence score, and measured `latency_ms`.
Every request increments Prometheus counters/histograms exposed at `/metrics`. The
HPA watches average CPU utilization across pods and scales the Deployment between 1
and 6 replicas.

## Repo layout

| Path | Purpose |
|---|---|
| `app/main.py` | FastAPI service: health check, inference endpoint, Prometheus metrics |
| `app/Dockerfile` | CPU-friendly container build (`python:3.11-slim`, CPU-only torch wheel) |
| `app/requirements.txt` | Python dependencies |
| `k8s/deployment.yaml` | Pod spec: resource requests/limits, readiness/liveness probes, commented GPU line |
| `k8s/service.yaml` | ClusterIP Service fronting the pods |
| `k8s/hpa.yaml` | HorizontalPodAutoscaler, CPU target, min 1 / max 6 |
| `loadtest/locustfile.py` | Locust load generator hitting `/predict` |
| `Makefile` | One-command workflow: cluster, build, load, deploy, forward, loadtest, hpa, clean |

## Run it on kind (exact steps)

Prerequisites: Docker running, `kind`, `kubectl`, and `make` on your PATH.

```bash
# 1. Create the local cluster
make cluster

# 2. Build the image (CPU-only, stub mode by default)
make build

# 3. Load the image into kind (no registry needed for local dev)
make load

# 4. Install metrics-server and apply the Deployment/Service/HPA
make deploy

# 5. In one terminal, forward the service to your laptop
make forward
# -> visit http://localhost:8080/healthz and http://localhost:8080/docs

# 6. In another terminal, drive load and watch it scale
make loadtest
make hpa      # watch REPLICAS climb as CPU utilization crosses 50%

# 7. Tear everything down
make clean
```

Quick manual check without Kubernetes at all:

```bash
cd app
USE_STUB=1 uvicorn main:app --port 8000 &
curl localhost:8000/healthz
curl -X POST localhost:8000/predict -H 'content-type: application/json' \
  -d '{"text": "I love this!"}'
```

## Switching to a real model

The service defaults to `USE_STUB=1` in the Deployment manifest so the demo needs no
model download and no GPU. To use the real HuggingFace model:

1. In `k8s/deployment.yaml`, change `USE_STUB` from `"1"` to `"0"` (or delete the env var
   — `main.py` defaults to real inference).
2. Optionally set `MODEL_NAME` to any HuggingFace sentiment/classification checkpoint.
3. Rebuild and reload the image (`make build load`), then re-apply (`make deploy`).

The first request after startup will download the model from HuggingFace Hub (needs
internet egress from the pod), then cache it in the container's filesystem for the
life of the pod.

## Switching to a real GPU node

This is designed to be a one-line change once you have a GPU-enabled node (e.g. a
cloud GPU node pool with the [NVIDIA device plugin](https://github.com/NVIDIA/k8s-device-plugin)
installed):

1. Uncomment the `nvidia.com/gpu: "1"` line under `resources.limits` in
   `k8s/deployment.yaml`. Kubernetes will now only schedule the pod onto a node that
   advertises a GPU.
2. Rebuild the image with a CUDA-enabled torch wheel — in `app/Dockerfile`, drop the
   `--extra-index-url https://download.pytorch.org/whl/cpu` flag (or point it at a
   `cu1xx` index) so `torch.cuda.is_available()` returns `True` inside the container.
3. No application code changes needed: `main.py` already calls
   `torch.cuda.is_available()` at startup and picks `cuda` automatically when present.

## Mapping files to resume bullets

- `app/main.py` + `app/Dockerfile` → *"Built and containerized a FastAPI model-inference
  service with health checks and Prometheus instrumentation, supporting seamless
  CPU/GPU device selection via PyTorch."*
- `k8s/deployment.yaml` → *"Defined Kubernetes resource requests/limits and
  readiness/liveness probes for a production-style inference workload, with a
  documented path to GPU scheduling via `nvidia.com/gpu` resource requests."*
- `k8s/hpa.yaml` → *"Configured Horizontal Pod Autoscaling on CPU utilization to
  automatically scale inference replicas from 1 to 6 under load."*
- `loadtest/locustfile.py` + `make loadtest` / `make hpa` → *"Load-tested the service
  with Locust and validated autoscaling behavior end-to-end on a local Kubernetes
  (kind) cluster."*
- `Makefile` → *"Automated the full local Kubernetes workflow (cluster creation, image
  build/load, deployment, load testing) into single-command `make` targets."*
