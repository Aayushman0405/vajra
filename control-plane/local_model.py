"""
Local CPU model service (Phi-3-mini)
Runs as separate K8s deployment
"""
import httpx
import time
from typing import Dict, Any, Optional

from config import settings

class LocalCPUModel:
    """Phi-3-mini running on OVH K8s"""
    
    def __init__(self):
        # FIXED: Use configured endpoint
        self.endpoint = settings.cpu_model_endpoint
        self.model_name = settings.cpu_model
    
    async def generate(self, prompt: str) -> str:
        """Generate response from local CPU model"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.endpoint,
                json={
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 300
                }
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    
    async def generate_with_metadata(self, prompt: str) -> Dict[str, Any]:
        """Generate with metadata for API response"""
        start = time.time()
        
        try:
            response = await self.generate(prompt)
            success = True
        except Exception as e:
            response = f"⚠️ CPU model temporarily unavailable: {str(e)}"
            success = False
        
        return {
            "response": response,
            "metadata": {
                "model": self.model_name,
                "inference_time_ms": int((time.time() - start) * 1000),
                "cold_start": False,
                "success": success
            }
        }

# Singleton instance
local_model = LocalCPUModel()

