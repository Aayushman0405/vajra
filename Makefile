.PHONY: help dev \
        build-control-plane deploy-control-plane \
        build-cpu-model deploy-cpu-model \
        deploy-aws-gpu \
        deploy-all \
        metrics demo init-cost-pvc cleanup-aws

REGISTRY=aayud
CONTROL_IMAGE=$(REGISTRY)/vajra-control-plane:latest
CPU_IMAGE=$(REGISTRY)/vajra-cpu-model:latest
NAMESPACE=vajra-system

help:
        @echo "Vajra - Intelligent LLM Control Plane (AWS Edition)"
        @echo ""
        @echo "Available Commands:"
        @echo "  make dev                   Run control plane locally"
        @echo "  make build-control-plane   Build & push control plane image"
        @echo "  make deploy-control-plane  Deploy control plane to Kubernetes"
        @echo "  make build-cpu-model       Build & push CPU model image"
        @echo "  make deploy-cpu-model      Deploy CPU model"
        @echo "  make deploy-aws-gpu        Deploy GPU node on AWS"
        @echo "  make deploy-all            Deploy everything"
        @echo "  make metrics               Port-forward Prometheus & Grafana"
        @echo "  make demo                  Run demo test suite"
        @echo "  make init-cost-pvc         Create cost persistence PVC"
        @echo "  make cleanup-aws           Shutdown AWS GPU instances"

# ------------------------
# Local Development
# ------------------------

dev:
        cd control-plane && uvicorn main:app --reload --host 0.0.0.0 --port 8000

# ------------------------
# Build Images
# ------------------------

build-control-plane:
        docker build -t $(CONTROL_IMAGE) control-plane/
        docker push $(CONTROL_IMAGE)

build-cpu-model:
        docker build -t $(CPU_IMAGE) -f gpu-node/cpu-model/Dockerfile gpu-node/cpu-model/
        docker push $(CPU_IMAGE)

# ------------------------
# Deployments
# ------------------------

deploy-control-plane:
        kubectl apply -f control-plane/k8s/namespace.yaml
        kubectl apply -f control-plane/k8s/aws-secrets.yaml  # NEW
        kubectl apply -f control-plane/k8s/deployment.yaml
        kubectl apply -f control-plane/k8s/ingress.yaml
        kubectl rollout status deployment/vajra-control-plane -n $(NAMESPACE)

deploy-cpu-model:
        kubectl apply -f control-plane/k8s/cpu-model.yaml
        kubectl rollout status deployment/vajra-cpu-model -n $(NAMESPACE)

deploy-aws-gpu:
        @echo "🚀 AWS GPU instances will be created on-demand"
        @echo "No manual deployment needed - control plane handles it"

deploy-all: deploy-cpu-model deploy-control-plane
        @echo "✅ Vajra fully deployed with AWS GPU on-demand"

init-cost-pvc:
        kubectl apply -f control-plane/k8s/vajra-data-pvc.yaml

cleanup-aws:
        @echo "🧹 Cleaning up AWS GPU instances..."
        python -c "from control-plane.gpu_manager.client import aws_gpu_manager; import asyncio; asyncio.run(aws_gpu_manager.terminate_instance())"

# ------------------------
# Observability
# ------------------------

metrics:
        @echo "Forwarding Prometheus → http://localhost:9090"
        @echo "Forwarding Grafana → http://localhost:3000"
        kubectl port-forward -n monitoring svc/prometheus 9090:9090 &
        kubectl port-forward -n monitoring svc/grafana 3000:3000 &

# ------------------------
# Demo
# ------------------------

demo:
        cd demo && ./test-requests.sh
