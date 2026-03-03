"""
Optimized Semantic Cache with automatic cleanup and size management
"""
import uuid
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, Range
import logging

from config import settings
from .embedder import embedder

logger = logging.getLogger(__name__)

class SemanticCache:
    def __init__(self):
        self.client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            timeout=10.0
        )
        self.collection_name = settings.qdrant_collection
        self.vector_size = 384  # all-MiniLM-L6-v2 dimension
        self.max_entries = getattr(settings, 'cache_max_entries', 1000)  # Safe default
        self._ensure_collection()
        self._start_cleanup_task()

    def _ensure_collection(self):
        """Create collection with optimized settings"""
        try:
            collections = self.client.get_collections().collections
            if not any(c.name == self.collection_name for c in collections):
                logger.info(f"Creating collection: {self.collection_name}")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.vector_size,
                        distance=Distance.COSINE
                    ),
                    optimizers_config=models.OptimizersConfigDiff(
                        default_segment_number=2,
                        memmap_threshold=10000,
                        indexing_threshold=50000
                    ),
                    wal_config=models.WalConfigDiff(
                        wal_capacity_mb=32,
                        wal_segments_ahead=0
                    )
                )
                logger.info(f"✅ Collection created: {self.collection_name}")
        except Exception as e:
            logger.error(f"Error ensuring collection: {e}")

    def _start_cleanup_task(self):
        """Start background cleanup task"""
        async def cleanup_loop():
            interval = getattr(settings, 'cache_cleanup_interval', 3600)
            while True:
                await asyncio.sleep(interval)
                try:
                    await self._cleanup_expired()
                    await self._enforce_size_limit()
                except Exception as e:
                    logger.error(f"Cleanup error: {e}")
        
        asyncio.create_task(cleanup_loop())

    async def _cleanup_expired(self):
        """Remove expired cache entries"""
        try:
            # Calculate expiration threshold
            max_ttl = max(
                getattr(settings, 'cache_ttl_code', 1800),
                getattr(settings, 'cache_ttl_factual', 43200),
                getattr(settings, 'cache_ttl_creative', 300)
            )
            expiry_time = (datetime.utcnow() - timedelta(seconds=max_ttl)).isoformat()
            
            # Delete expired entries
            result = self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=Filter(
                        must=[
                            FieldCondition(
                                key="cached_at",
                                range=Range(
                                    lt=expiry_time
                                )
                            )
                        ]
                    )
                )
            )
            if result.status == "completed":
                logger.info(f"🧹 Cleaned up expired cache entries")
        except Exception as e:
            logger.error(f"Error cleaning up expired entries: {e}")

    async def _enforce_size_limit(self):
        """Enforce maximum cache size"""
        try:
            collection_info = self.client.get_collection(self.collection_name)
            current_count = collection_info.points_count
            
            if current_count > self.max_entries:
                to_delete = current_count - self.max_entries
                
                scroll_result = self.client.scroll(
                    collection_name=self.collection_name,
                    limit=to_delete,
                    with_payload=True,
                    with_vectors=False,
                    order_by=models.OrderBy(
                        key="cached_at",
                        direction=models.Direction.ASC
                    )
                )
                
                if scroll_result[0]:
                    point_ids = [point.id for point in scroll_result[0]]
                    self.client.delete(
                        collection_name=self.collection_name,
                        points_selector=models.PointIdsList(
                            points=point_ids
                        )
                    )
                    logger.info(f"🧹 Enforced size limit: removed {len(point_ids)} oldest entries")
        except Exception as e:
            logger.error(f"Error enforcing size limit: {e}")

    def _get_cache_ttl(self, query_type: str) -> int:
        """Dynamic TTL based on query type"""
        ttl_map = {
            "code": getattr(settings, 'cache_ttl_code', 1800),
            "factual": getattr(settings, 'cache_ttl_factual', 43200),
            "creative": getattr(settings, 'cache_ttl_creative', 300)
        }
        return ttl_map.get(query_type, getattr(settings, 'cache_ttl_factual', 43200))

    async def search(
        self,
        query: str,
        threshold: float = None
    ) -> Optional[Dict[str, Any]]:
        """Search for similar cached response"""
        if threshold is None:
            threshold = getattr(settings, 'cache_threshold', 0.95)
            
        try:
            query_vector = await embedder.encode(query)

            search_result = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=1,
                score_threshold=threshold,
                with_payload=True
            )

            if not search_result:
                return None

            hit = search_result[0]
            payload = hit.payload

            # Check if expired
            cached_at = datetime.fromisoformat(payload["cached_at"])
            ttl = self._get_cache_ttl(payload.get("query_type", "factual"))
            if datetime.utcnow() - cached_at > timedelta(seconds=ttl):
                # Expired, delete it
                self.client.delete(
                    collection_name=self.collection_name,
                    points_selector=models.PointIdsList(
                        points=[hit.id]
                    )
                )
                return None

            logger.info(f"🎯 Cache hit! Similarity: {hit.score:.3f}")
            return {
                "response": payload["response"],
                "similarity": hit.score,
                "cached_at": payload["cached_at"],
                "query_type": payload.get("query_type", "factual"),
                "id": hit.id
            }
        except Exception as e:
            logger.error(f"Cache search error: {e}")
            return None

    async def insert(
        self,
        query: str,
        response: str,
        query_type: str = "factual",
        metadata: Optional[Dict] = None
    ) -> Optional[str]:
        """Cache a query-response pair"""
        try:
            vector = await embedder.encode(query)

            payload = {
                "query": query[:500],
                "response": response,
                "query_type": query_type,
                "cached_at": datetime.utcnow().isoformat(),
                "metadata": metadata or {}
            }

            point_id = str(uuid.uuid4())
            point = PointStruct(
                id=point_id,
                vector=vector,
                payload=payload
            )

            self.client.upsert(
                collection_name=self.collection_name,
                points=[point],
                wait=False
            )

            logger.info(f"💾 Cached response with ID: {point_id}")
            return point_id
        except Exception as e:
            logger.error(f"Cache insert error: {e}")
            return None

    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        try:
            collection_info = self.client.get_collection(self.collection_name)
            return {
                "total_points": collection_info.points_count,
                "vectors_count": collection_info.vectors_count,
                "segments_count": collection_info.segments_count,
                "status": collection_info.status,
                "optimizer_status": collection_info.optimizer_status
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {"error": str(e)}

    def health_check(self) -> bool:
        """Synchronous health check"""
        try:
            self.client.get_collections()
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

# Singleton instance
cache = SemanticCache()
