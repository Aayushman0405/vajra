import time
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

from cache.qdrant_client import cache
from decision_engine import decision_engine
from gpu_manager.client import aws_gpu_manager
from local_model import local_model
from metrics import requests_total, cache_hits, cache_misses, decisions_total, response_time
from config import settings
from auth import verify_api_key

router = APIRouter()

# Pydantic models
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 500
    stream: Optional[bool] = False

class ChatResponse(BaseModel):
    id: str
    choices: List[Dict[str, Any]]
    usage: Dict[str, Any]
    model: str
    target: str
    cached: bool = False

@router.get("/health")
async def health_check():
    """Simple health check endpoint for probes"""
    return JSONResponse(
        status_code=200,
        content={"status": "healthy", "service": "vajra-control-plane"}
    )

@router.get("/")
async def root():
    """Root endpoint"""
    return JSONResponse(
        content={
            "name": "Vajra Control Plane",
            "version": "1.0.0",
            "status": "running"
        }
    )

@router.post("/chat/completions", response_model=ChatResponse)
async def chat_completion(
    request: ChatRequest,
    api_key: str = Depends(verify_api_key)
):
    """Main chat completion endpoint with intelligent routing"""
    start_time = time.time()
    requests_total.inc()
    
    try:
        # Get the last user message
        if not request.messages:
            raise HTTPException(status_code=400, detail="No messages provided")
        
        user_message = request.messages[-1].content
        
        # Check cache first
        cached_response = await cache.search(user_message)
        if cached_response:
            cache_hits.inc()
            response_time.labels(model_type="cache").observe(time.time() - start_time)
            
            return ChatResponse(
                id=f"cache-{uuid.uuid4().hex[:8]}",
                choices=[{
                    "message": {"role": "assistant", "content": cached_response["response"]},
                    "finish_reason": "stop"
                }],
                usage={
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0
                },
                model="cache",
                target="cache",
                cached=True
            )
        
        cache_misses.inc()
        
        # Get budget info from cost engine
        try:
            from cost_engine import cost_engine
            today_cost = await cost_engine.get_today_gpu_cost()
            budget_remaining = max(0, settings.daily_budget - today_cost)
        except:
            budget_remaining = settings.daily_budget
        
        # Analyze query for routing decision
        decision = await decision_engine.analyze(
            query=user_message,
            budget_remaining=budget_remaining
        )
        
        decisions_total.labels(target=decision["target"]).inc()
        
        # Use local CPU model (GPU not implemented yet)
        response_data = await local_model.generate_with_metadata(user_message)
        model_used = settings.cpu_model
        target_used = "cpu"
        
        # Cache the response for future use
        try:
            await cache.insert(
                query=user_message,
                response=response_data["response"],
                query_type=decision["query_type"],
                metadata={
                    "model": model_used,
                    "target": target_used,
                    "confidence": decision.get("confidence", 0.5)
                }
            )
        except Exception as e:
            logger.warning(f"Cache insert failed: {e}")
        
        # Record metrics
        response_time.labels(model_type=target_used).observe(time.time() - start_time)
        
        return ChatResponse(
            id=f"{target_used}-{uuid.uuid4().hex[:8]}",
            choices=[{
                "message": {"role": "assistant", "content": response_data["response"]},
                "finish_reason": "stop"
            }],
            usage={
                "prompt_tokens": len(user_message.split()),
                "completion_tokens": len(response_data["response"].split()),
                "total_tokens": len(user_message.split()) + len(response_data["response"].split()),
                "inference_time_ms": response_data["metadata"].get("inference_time_ms", 0)
            },
            model=model_used,
            target=target_used,
            cached=False
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat completion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/models")
async def list_models(api_key: str = Depends(verify_api_key)):
    """List available models"""
    return JSONResponse(
        content={
            "models": [
                {
                    "id": settings.cpu_model,
                    "name": "Phi-3-mini (CPU)",
                    "type": "cpu",
                    "description": "Efficient model for simple queries"
                },
                {
                    "id": "llama-3-8b",
                    "name": "Llama-3-8b (GPU)",
                    "type": "gpu",
                    "description": "Powerful model for complex reasoning"
                }
            ]
        }
    )

@router.get("/metrics/cost")
async def get_cost_metrics(api_key: str = Depends(verify_api_key)):
    """Get current cost metrics"""
    try:
        from cost_engine import cost_engine
        today_cost = await cost_engine.get_today_gpu_cost()
        remaining = settings.daily_budget - today_cost
        
        return JSONResponse(
            content={
                "daily_budget": settings.daily_budget,
                "today_cost": round(today_cost, 4),
                "remaining_budget": round(remaining, 4),
                "budget_percent": round((today_cost / settings.daily_budget) * 100, 2)
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@router.get("/cache/stats")
async def get_cache_stats(api_key: str = Depends(verify_api_key)):
    """Get cache statistics"""
    try:
        stats = await cache.get_stats()
        return JSONResponse(content=stats)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )
