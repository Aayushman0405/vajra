import numpy as np
import asyncio
from sentence_transformers import SentenceTransformer
from functools import lru_cache
from config import settings

class EmbedderService:
    def __init__(self, model_name: str = settings.embedding_model):
        self.model_name = model_name
        self.model = None
    
    def _load_model(self):
        """Lazy load the model"""
        if self.model is None:
            print(f"Loading embedding model: {self.model_name}")
            self.model = SentenceTransformer(self.model_name)
            print("Embedding model loaded")
        return self.model
    
    @lru_cache(maxsize=1000)
    def _encode_sync(self, text: str) -> list:
        """Synchronous encoding - called from thread pool"""
        model = self._load_model()
        embedding = model.encode(text, normalize_embeddings=True)
        return embedding.tolist()
    
    async def encode(self, text: str) -> list:
        """FIXED: Non-blocking async embedding using thread pool"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._encode_sync, text)
    
    async def encode_batch(self, texts: list[str]) -> list[list[float]]:
        """FIXED: Non-blocking batch embedding"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._encode_batch_sync, texts)
    
    def _encode_batch_sync(self, texts: list[str]) -> list[list[float]]:
        """Synchronous batch encoding"""
        model = self._load_model()
        embeddings = model.encode(texts, normalize_embeddings=True)
        return [emb.tolist() for emb in embeddings]

# Singleton instance
embedder = EmbedderService()

