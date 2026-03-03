# Vajra - Intelligent LLM Control Plane

Vajra is an intelligent traffic controller for LLM models that optimizes costs by intelligently routing queries between CPU and GPU instances.

## Architecture

- **Control Plane**: FastAPI service that makes routing decisions
- **CPU Model**: Runs Phi-3-mini on OVH Kubernetes
- **GPU Model**: On-demand AWS GPU instances (g4dn.xlarge)
- **Semantic Cache**: Qdrant for caching similar queries
- **Cost Engine**: Tracks GPU usage with RGW persistence

## Prerequisites

- Kubernetes cluster (OVH)
- AWS account with EC2 access
- Rook-Ceph with RGW endpoint
- kubectl configured
- Docker

## Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/Aayushman0405/vajra.git
   cd vajra

Set up secrets

# Copy and fill in your secrets
cp control-plane/k8s/aws-secrets.yaml.template control-plane/k8s/aws-secrets.yaml
cp control-plane/.env.template control-plane/.env
cp terraform/terraform.tfvars.template terraform/terraform.tfvars

# Edit with your actual credentials
vim control-plane/k8s/aws-secrets.yaml
vim control-plane/.env


Deploy with Make

# Build and push images
make build-control-plane
make build-cpu-model

# Deploy to Kubernetes
make deploy-all

Test the deployment:
make demo

Configuration
Environment Variables
Variable	Description	Required
VAJRA_API_KEY	API authentication key	Yes
VAJRA_AWS_ACCESS_KEY_ID	AWS access key	Yes
VAJRA_AWS_SECRET_ACCESS_KEY	AWS secret key	Yes
VAJRA_HF_TOKEN	HuggingFace token	Yes
VAJRA_RGW_ACCESS_KEY	RGW access key	Yes
VAJRA_RGW_SECRET_KEY	RGW secret key	Yes
VAJRA_DAILY_BUDGET	Daily GPU budget	No (default: $5.00)

