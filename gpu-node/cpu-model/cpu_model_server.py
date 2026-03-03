"""
CPU Model Server for Vajra
Runs Phi-3-mini on CPU
"""
import os
import time
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import uvicorn

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
MODEL_NAME = os.getenv("MODEL_NAME", "microsoft/Phi-3-mini-4k-instruct")
NUM_THREADS = int(os.getenv("NUM_CPU_THREADS", "4"))

# Set CPU threads
torch.set_num_threads(NUM_THREADS)

logger.info(f"🚀 Starting CPU Model Server")
logger.info(f"📦 Model: {MODEL_NAME}")
logger.info(f"⚙️  CPU Threads: {NUM_THREADS}")

app = FastAPI(title="Vajra CPU Model")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 500

class ChatCompletionResponse(BaseModel):
    id: str
    choices: List[Dict[str, Any]]
    usage: Dict[str, Any]

class CPUModel:
    def __init__(self):
        logger.info(f"Loading model: {MODEL_NAME}")
        start = time.time()
        
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                MODEL_NAME,
                trust_remote_code=True
            )
            logger.info("✅ Tokenizer loaded")
            
            self.model = AutoModelForCausalLM.from_pretrained(
                MODEL_NAME,
                torch_dtype=torch.float32,
                trust_remote_code=True,
                low_cpu_mem_usage=True
            )
            logger.info(f"✅ Model loaded in {time.time() - start:.2f}s")
        except Exception as e:
            logger.error(f"❌ Failed to load model: {e}")
            raise

    def generate(self, prompt: str, **kwargs) -> Dict[str, Any]:
        start = time.time()
        logger.info(f"Generating response for prompt: {prompt[:50]}...")
        
        inputs = self.tokenizer(prompt, return_tensors="pt")
        
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=kwargs.get("max_tokens", 500),
                temperature=kwargs.get("temperature", 0.7),
                do_sample=True,
                pad_token_id=self.tokenizer.eos_token_id
            )
        
        response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        response = response[len(prompt):].strip()
        
        prompt_tokens = len(inputs['input_ids'][0])
        completion_tokens = len(outputs[0]) - prompt_tokens
        
        latency = time.time() - start
        logger.info(f"Generated {completion_tokens} tokens in {latency:.2f}s")
        
        return {
            "id": f"cpu-{int(time.time())}",
            "choices": [{
                "message": {"role": "assistant", "content": response},
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "total_time": int(latency * 1000)
            }
        }

# Initialize model at startup
logger.info("Initializing model...")
model = CPUModel()
logger.info("✅ Model initialization complete")

@app.get("/health")
async def health():
    return {"status": "healthy", "model": MODEL_NAME}

@app.post("/v1/chat/completions")
async def chat_completion(request: ChatCompletionRequest):
    prompt = request.messages[-1].content
    return model.generate(
        prompt,
        temperature=request.temperature,
        max_tokens=request.max_tokens
    )

@app.get("/")
async def root():
    return {"service": "Vajra CPU Model", "model": MODEL_NAME}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
