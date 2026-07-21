CLUSTER_NAME := inference-platform
IMAGE := inference-service:local
NAMESPACE := default
LOCAL_PORT := 8080

.PHONY: cluster build load deploy forward loadtest hpa clean

## Create a local kind cluster (no-op if it already exists).
cluster:
	@if kind get clusters | grep -q "^$(CLUSTER_NAME)$$"; then \
		echo "kind cluster '$(CLUSTER_NAME)' already exists"; \
	else \
		kind create cluster --name $(CLUSTER_NAME); \
	fi

## Build the CPU-friendly inference image.
build:
	docker build -t $(IMAGE) ./app

## Load the locally built image into the kind cluster (no registry needed).
load:
	kind load docker-image $(IMAGE) --name $(CLUSTER_NAME)

## Install metrics-server (needed for HPA) and apply all manifests.
deploy:
	kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
	kubectl patch deployment metrics-server -n kube-system --type=json \
		-p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]' || true
	kubectl apply -f k8s/deployment.yaml
	kubectl apply -f k8s/service.yaml
	kubectl apply -f k8s/hpa.yaml
	kubectl rollout status deployment/inference-service --timeout=120s

## Port-forward the service to localhost so it's reachable outside the cluster.
forward:
	kubectl port-forward svc/inference-service $(LOCAL_PORT):80

## Run a headless Locust load test against the port-forwarded service.
loadtest:
	pip install -q -r loadtest/requirements.txt
	locust -f loadtest/locustfile.py --host http://localhost:$(LOCAL_PORT) \
		--headless -u 50 -r 10 -t 2m

## Watch the HPA compute replicas in real time (Ctrl+C to stop).
hpa:
	kubectl get hpa inference-service --watch

## Tear down the kind cluster entirely.
clean:
	kind delete cluster --name $(CLUSTER_NAME)
