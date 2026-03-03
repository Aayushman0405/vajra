# control-plane/main.py
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import asyncio
from datetime import datetime
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger("vajra")

from router import router as chat_router
from metrics import metrics_router
from config import settings
from auth import verify_api_key
from gpu_manager.client import aws_gpu_manager
from cache.qdrant_client import cache
from cost_engine import cost_engine

# Rate limiting
from collections import defaultdict
rate_limit_store = defaultdict(list)
RATE_LIMIT = 60
RATE_LIMIT_WINDOW = 60

app = FastAPI(
    title="Vajra - Intelligent LLM Control Plane",
    description="AI traffic controller for cost-efficient model inference",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting middleware
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    try:
        # Simple rate limiting
        client_ip = request.client.host
        now = time.time()
        
        # Clean old entries
        rate_limit_store[client_ip] = [t for t in rate_limit_store[client_ip] if now - t < RATE_LIMIT_WINDOW]
        
        # Check rate limit
        if len(rate_limit_store[client_ip]) >= RATE_LIMIT:
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded"}
            )
        
        # Add current request
        rate_limit_store[client_ip].append(now)
        
        # Process request
        response = await call_next(request)
        return response
    except Exception as e:
        logger.error(f"Middleware error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"}
        )

@app.on_event("startup")
async def startup_event():
    """Initialize services"""
    logger.info("🚀 Vajra Control Plane starting up...")

    # Check AWS connection
    try:
        health = await aws_gpu_manager.health_check()
        if health["status"] == "healthy":
            logger.info(f"✅ AWS GPU connected")
        else:
            logger.info(f"⏳ AWS GPU ready for on-demand provisioning")
    except Exception as e:
        logger.warning(f"⚠️ AWS GPU check failed: {e}")

    try:
        await cost_engine.initialize()
    except Exception as e:
        logger.error(f"⚠️ Cost engine initialization error: {e}")
    
    logger.info("✅ Vajra Control Plane ready")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean shutdown"""
    logger.info("🛑 Vajra Control Plane shutting down...")
    try:
        # Shutdown GPU instance to save costs
        await aws_gpu_manager.shutdown_instance()
        await cost_engine.close()
    except Exception as e:
        logger.error(f"⚠️ Shutdown error: {e}")
    logger.info("✅ Shutdown complete")

@app.get("/health")
async def health():
    """Comprehensive health check"""
    try:
        qdrant_healthy = cache.health_check()
        
        # Get cost engine status safely
        try:
            today_cost = await cost_engine.get_today_gpu_cost()
        except:
            today_cost = 0.0
        
        # Get AWS health safely
        try:
            aws_health = await aws_gpu_manager.health_check()
            aws_status = aws_health["status"]
        except:
            aws_status = "unknown"
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "healthy" if qdrant_healthy else "degraded",
                "service": "vajra-control-plane",
                "version": "1.0.0",
                "checks": {
                    "qdrant": "up" if qdrant_healthy else "down",
                    "aws_gpu": aws_status,
                    "cost_engine": "initialized",
                    "cache_collection": settings.qdrant_collection
                },
                "metrics": {
                    "today_gpu_cost": today_cost,
                    "daily_budget": settings.daily_budget
                },
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )

@app.get("/")
async def root():
    """Root endpoint"""
    return JSONResponse(
        content={
            "name": "Vajra",
            "description": "Intelligent Air Traffic Controller for AI Models",
            "documentation": "/docs",
            "version": "1.0.0"
        }
    )

@app.get("/ready")
async def ready():
    """Readiness probe endpoint"""
    return JSONResponse(
        status_code=200,
        content={"status": "ready"}
    )

@app.get("/live")
async def live():
    """Liveness probe endpoint"""
    return JSONResponse(
        status_code=200,
        content={"status": "alive"}
    )

# Include routers
app.include_router(chat_router, prefix="/v1", dependencies=[Depends(verify_api_key)])
app.include_router(metrics_router, prefix="/metrics")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )
