Vajra - Intelligent LLM Control Plane

📋 Overview
Vajra is an intelligent AI traffic controller that optimizes LLM inference costs by intelligently routing queries between CPU and GPU models. It acts as a smart proxy that decides whether to use a lightweight local model (CPU) or a powerful cloud GPU model based on query complexity, budget constraints, and cached responses.

Named after the mythical "diamond thunderbolt" - representing the perfect balance of power and precision.

🏗 Architecture

┌─────────────────────────────────────────────────────────────────────┐
│                         CLIENT REQUESTS                              │
│                         (REST API / Dashboard)                       │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      VAJRA CONTROL PLANE                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  Auth Layer  │─▶│Rate Limiting│─▶│   Decision Engine        │  │
│  │  (API Keys)  │  │   (60/min)  │  │ • Query analysis         │  │
│  └──────────────┘  └──────────────┘  │ • Complexity scoring    │  │
│                                       │ • Budget checking       │  │
│  ┌─────────────────────────────────┐  │ • Routing decisions     │  │
│  │     Semantic Cache (Qdrant)     │  └───────────┬──────────────┘  │
│  │  • Embedding-based search       │              │                   │
│  │  • Automatic TTL management     │◀─────────────┘                   │
│  │  • Size-limited cache (1000)    │                                   │
│  └─────────────────────────────────┘                                   │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    ▼                           ▼
┌─────────────────────────────┐    ┌─────────────────────────────┐
│    CPU MODEL (TinyLlama)    │    │    GPU MODEL (AWS Lambda)   │
│  • Local Kubernetes pod      │    │  • On-demand EC2 instances │
│  • 1.1B parameters           │    │  • Llama-3-8b              │
│  • 2-3Gi memory              │    │  • Auto-scaling to zero    │
│  • Always available          │    │  • Cost: $0.526/hour       │
└─────────────────────────────┘    └─────────────────────────────┘

🧠 Core Logic
Decision Engine Heuristics

Length Score (30% weight)
Short (<50 chars): Simple query → CPU
Medium (50-150): Moderate complexity
Long (>300): Complex → GPU

Keyword Score (50% weight)
Code patterns: write function, leetcode, debug → GPU
Reasoning: explain concept, prove that, compare → GPU
Creative: write poem, create story → Mixed
Default: Simple factual → CPU

Budget Check (20% weight)
Daily budget: $5.00
GPU cost: $0.526/hour (spot pricing)
Conserves GPU when <$0.50 remaining


Example Decision Flow
Query: "Write a Python function to reverse a linked list"
→ Length: 45 chars (score: 0.2)
→ Keywords: 'write', 'function', 'reverse linked list' (score: 0.9)
→ Budget: $4.50 remaining (within limit)
→ Final GPU score: 0.65 → Route to GPU


💾 Storage Strategy
Optimized Resource Usage

Component	   Storage Type	Size	Purpose
Qdrant Cache	Ceph RBD (PVC)	2Gi	Semantic cache with auto-cleanup
Cost Tracking	RGW (S3)	1Gi	Daily budget persistence
Model Cache	   Ceph RBD (PVC)	20Gi	HuggingFace model storage


Cache Management
TTL by query type: Code (30min), Factual (12hr), Creative (5min)

Max entries: 1000 (prevents bloat)

Auto-cleanup: Every 6 hours via CronJob

Similarity threshold: 0.95 for cache hits

🚀 Getting Started
Prerequisites
Kubernetes cluster (v1.29+)
Rook-Ceph storage
RGW object storage
AWS account (for GPU instances)

🔌 API Reference
Base URL
https://vajra.aayushmandev.space


Authentication
All API endpoints require an API key header:
X-API-Key: 70204bf9039ea021d971b2932693030b909a5c5e83c4db7ae9e803f1f651884d

Interactive API Docs
https://vajra.aayushmandev.space/docs
FastAPI Swagger UI with full endpoint documentation and test interface.

Endpoints
1. Chat Completion
POST /v1/chat/completions
Content-Type: application/json
X-API-Key: your-api-key

{
  "messages": [
    {"role": "user", "content": "What is Kubernetes?"}
  ],
  "temperature": 0.7,
  "max_tokens": 500
}


Response:
{
  "id": "cpu-abc123",
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "Kubernetes is an open-source container orchestration platform..."
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 5,
    "completion_tokens": 150,
    "total_tokens": 155,
    "inference_time_ms": 2345
  },
  "model": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
  "target": "cpu",
  "cached": false
}


2. List Models
GET /v1/models
X-API-Key: your-api-key

Response:
{
  "models": [
    {
      "id": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
      "name": "TinyLlama (CPU)",
      "type": "cpu",
      "description": "Lightweight 1.1B model for simple queries"
    },
    {
      "id": "llama-3-8b",
      "name": "Llama-3-8b (GPU)",
      "type": "gpu",
      "description": "Powerful model for complex reasoning"
    }
  ]
}


3. Cache Statistics
GET /v1/cache/stats
X-API-Key: your-api-key


4. Cost Metrics
GET /v1/metrics/cost
X-API-Key: your-api-key

5. Health Checks
GET /health
GET /ready
GET /live

🧪 Testing Guide
1. Quick Test with curl
# Set your API key
API_KEY="70204bf9039ea021d971b2932693030b909a5c5e83c4db7ae9e803f1f651884d"

# Test simple query (should route to CPU)
curl -X POST https://vajra.aayushmandev.space/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "messages": [{"role": "user", "content": "What is Docker?"}]
  }'

# Test complex query (should route to GPU)
curl -X POST https://vajra.aayushmandev.space/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "messages": [{"role": "user", "content": "Write a Python function to implement a binary search tree"}]
  }'

  2. Test Cache Mechanism
# First request (cache miss)
curl -X POST https://vajra.aayushmandev.space/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "messages": [{"role": "user", "content": "What is Kubernetes?"}]
  }'

# Second request (cache hit) - look for "cached": true in response
curl -X POST https://vajra.aayushmandev.space/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "messages": [{"role": "user", "content": "What is Kubernetes?"}]
  }'


3. Interactive Testing
https://vajra.aayushmandev.space/docs
Features:
Try all endpoints interactively
See request/response schemas
Authenticate with API key
View model schemas

4. Monitor Performance
# Check cache efficiency
curl -H "X-API-Key: $API_KEY" https://vajra.aayushmandev.space/v1/cache/stats

# Check daily GPU spend
curl -H "X-API-Key: $API_KEY" https://vajra.aayushmandev.space/v1/metrics/cost

# Prometheus metrics (no auth)
curl https://vajra.aayushmandev.space/metrics

📊 Key Features
Intelligent Routing
Dynamic decision engine with configurable weights
Budget-aware routing with daily spend limits
Query complexity analysis using keyword patterns
Confidence scoring for routing decisions

Cost Optimization
GPU on-demand: EC2 instances auto-scale to zero
Semantic caching: Reduce redundant API calls
Budget enforcement: Hard stop at daily limit
Cost tracking: Persistent storage in RGW

Performance
Cache hit rate: Typically 30-40% for repeated queries
Response time: CPU: 2-5s, GPU: 5-10s, Cache: <100ms
Auto-scaling: GPU instances spin up in 2-3 minutes

Observability
Prometheus metrics for all operations
Request counting by target (cpu/gpu/cache)
Response time histograms per model type
Cost tracking with daily gauges

🛠 Tech Stack
Core
FastAPI - High-performance async framework
Uvicorn - ASGI server
Pydantic - Data validation

Storage
Qdrant - Vector similarity search
Ceph RBD - Block storage for cache
RGW (S3) - Object storage for cost data
Sentence-Transformers - Embedding generation

ML Models
TinyLlama-1.1B - CPU model (local)
Phi-3-mini - Alternative CPU model
Llama-3-8b - GPU model (AWS)
all-MiniLM-L6-v2 - Embedding model

Infrastructure
Kubernetes - Container orchestration
Rook-Ceph - Distributed storage
Prometheus - Metrics collection
Ingress-NGINX - Load balancing
Cert-Manager - TLS certificates

AWS Integration
EC2 - GPU instances (g4dn.xlarge)
ECR - Container registry
Boto3 - AWS SDK


📈 Performance Benchmarks
Query    Type	     CPU Time  GPU Time	Cache Time	Savings
Simple   factual	  2.3s	   5.1s	   45ms	      98%
Code     generation 4.7s	   6.2s	   52ms	      97%
Complex  reasoning  8.9s	   7.8s	   48ms	      99%
Creative writing	  5.2s	   6.5s	   51ms	      98%

🔒 Security
API Key authentication for all endpoints
Rate limiting: 60 requests/minute per IP
TLS encryption via Let's Encrypt
Secrets management via Kubernetes secrets
CORS configured for web access

🎯 Use Cases
Cost-sensitive AI applications - Start with CPU, use GPU only when needed
High-volume chatbots - Cache common responses
Development environments - Budget enforcement
Multi-tenant AI services - Per-tenant budget tracking
Hybrid cloud deployments - On-prem CPU + cloud GPU


📚 Additional Resources
Swagger UI: https://vajra.aayushmandev.space/docs
Prometheus: https://vajra.aayushmandev.space/metrics





