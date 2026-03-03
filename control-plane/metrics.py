from prometheus_client import Counter, Histogram, Gauge, generate_latest
from fastapi import APIRouter, Response
import time

metrics_router = APIRouter()

# Request metrics
requests_total = Counter(
    'vajra_requests_total',
    'Total number of requests'
)

cache_hits = Counter(
    'vajra_cache_hits_total',
    'Total cache hits'
)

cache_misses = Counter(
    'vajra_cache_misses_total',
    'Total cache misses'
)

# Decision metrics
decisions_total = Counter(
    'vajra_decisions_total',
    'Total routing decisions',
    ['target']
)

# GPU metrics
cold_starts = Counter(
    'vajra_cold_starts_total',
    'Total GPU cold starts'
)

gpu_idle_shutdowns = Counter(
    'vajra_gpu_idle_shutdowns_total',
    'Total idle shutdowns'
)

gpu_runtime_seconds = Counter(
    'vajra_gpu_runtime_seconds_total',
    'Total cumulative GPU runtime in seconds'
)

# Response time metrics
response_time = Histogram(
    'vajra_response_time_seconds',
    'Response time in seconds',
    ['model_type'],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
)

# Cost metrics
daily_gpu_cost = Gauge(
    'vajra_daily_gpu_cost_usd',
    'Daily GPU cost in USD'
)

estimated_savings = Gauge(
    'vajra_estimated_savings_usd',
    'Estimated savings vs 24/7 GPU'
)

@metrics_router.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain")

