"""
Cost tracking and budget management for Vajra
OPTIMIZED: Uses RGW object storage for HA persistence
"""
import json
import asyncio
import aiobotocore.session
from datetime import datetime, date
from typing import Dict, Optional, Any
import logging
from botocore.config import Config
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
from metrics import daily_gpu_cost

logger = logging.getLogger(__name__)

class CostEngine:
    def __init__(self):
        self.daily_budget = settings.daily_budget
        self.gpu_cost_per_hour = settings.aws_gpu_cost_per_hour
        
        # RGW Configuration
        self.rgw_endpoint = settings.rgw_endpoint
        self.bucket = settings.rgw_bucket
        self.key = "vajra-cost-tracking.json"
        
        # Local cache for performance
        self._daily_spend = 0.0
        self._last_reset = date.today()
        self._last_sync = datetime.now()
        self._sync_interval = 300  # Sync every 5 minutes
        self._dirty = False
        
        # Initialize session
        self._session = None
        self._client = None
        
        # Start background sync
        self._start_background_sync()

    async def _get_client(self):
        """Get or create RGW client"""
        if not self._session:
            self._session = aiobotocore.session.get_session()
            
        if not self._client:
            # FIXED: Create client properly using context manager
            client_creator = self._session.create_client(
                's3',
                endpoint_url=self.rgw_endpoint,
                aws_access_key_id=settings.rgw_access_key,
                aws_secret_access_key=settings.rgw_secret_key,
                config=Config(
                    signature_version='s3v4',
                    s3={'addressing_style': 'path'} if settings.rgw_path_style else 'auto'
                )
            )
            # Use the client creator as a context manager
            self._client = await client_creator.__aenter__()
            
        return self._client

    async def _ensure_bucket(self):
        """Create bucket if it doesn't exist"""
        try:
            client = await self._get_client()
            try:
                await client.head_bucket(Bucket=self.bucket)
                logger.info(f"✅ Bucket {self.bucket} exists")
            except Exception as e:
                error_code = None
                if hasattr(e, 'response') and e.response.get('Error', {}).get('Code'):
                    error_code = e.response['Error']['Code']
                
                if error_code == '404' or 'NoSuchBucket' in str(e):
                    logger.info(f"📁 Creating bucket {self.bucket}")
                    await client.create_bucket(
                        Bucket=self.bucket,
                        CreateBucketConfiguration={
                            'LocationConstraint': settings.rgw_region
                        }
                    )
                else:
                    logger.warning(f"⚠️ Bucket check failed: {e}")
        except Exception as e:
            logger.error(f"❌ Failed to ensure bucket: {e}")

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=5)
    )
    async def _load_from_rgw(self) -> Optional[Dict]:
        """Load cost state from RGW with retries"""
        try:
            client = await self._get_client()
            try:
                response = await client.get_object(
                    Bucket=self.bucket,
                    Key=self.key
                )
                data = await response['Body'].read()
                return json.loads(data)
            except Exception as e:
                error_code = None
                if hasattr(e, 'response') and e.response.get('Error', {}).get('Code'):
                    error_code = e.response['Error']['Code']
                
                if error_code == 'NoSuchKey' or 'NoSuchKey' in str(e):
                    logger.info("📁 No existing cost state found")
                    return None
                logger.warning(f"⚠️ Error loading from RGW: {e}")
                return None
        except Exception as e:
            logger.warning(f"⚠️ Failed to connect to RGW: {e}")
            return None

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=5)
    )
    async def _save_to_rgw(self, data: Dict):
        """Save cost state to RGW with retries"""
        try:
            client = await self._get_client()
            await client.put_object(
                Bucket=self.bucket,
                Key=self.key,
                Body=json.dumps(data, indent=2),
                ContentType='application/json'
            )
            logger.debug(f"💾 Saved cost state to RGW: ${data['spend']:.4f}")
        except Exception as e:
            logger.warning(f"⚠️ Error saving to RGW: {e}")

    def _start_background_sync(self):
        """Start background task to sync with RGW periodically"""
        async def sync_loop():
            while True:
                await asyncio.sleep(self._sync_interval)
                try:
                    if self._dirty:
                        await self._sync_to_rgw()
                except Exception as e:
                    logger.error(f"⚠️ Background sync failed: {e}")
        
        asyncio.create_task(sync_loop())

    async def _sync_to_rgw(self):
        """Sync local state to RGW"""
        try:
            await self._save_to_rgw({
                'date': self._last_reset.isoformat(),
                'spend': round(self._daily_spend, 6),
                'last_updated': datetime.utcnow().isoformat()
            })
            self._last_sync = datetime.now()
            self._dirty = False
            logger.info(f"💾 Synced cost state to RGW: ${self._daily_spend:.4f}")
        except Exception as e:
            logger.error(f"⚠️ Sync failed: {e}")

    async def initialize(self):
        """Initialize cost engine"""
        try:
            # Try to load from RGW
            data = await self._load_from_rgw()
            
            if data:
                saved_date = datetime.fromisoformat(data['date']).date()
                
                if saved_date == date.today():
                    self._daily_spend = data['spend']
                    self._last_reset = saved_date
                    logger.info(f"💰 Loaded cost state: ${self._daily_spend:.4f} spent today")
                else:
                    logger.info(f"📅 New day - resetting cost counter")
                    self._daily_spend = 0.0
                    self._last_reset = date.today()
                    self._dirty = True
            else:
                logger.info(f"📁 No existing cost state, starting fresh")
                self._daily_spend = 0.0
                self._last_reset = date.today()
                self._dirty = True
            
            # Update metrics
            daily_gpu_cost.set(self._daily_spend)
            
            logger.info(f"💰 Cost engine initialized. Daily budget: ${self.daily_budget}")
            logger.info(f"   Today's spend: ${self._daily_spend:.4f}")
            logger.info(f"   Storage: RGW bucket {self.bucket}/{self.key}")
            
            # Try to ensure bucket exists in background
            asyncio.create_task(self._ensure_bucket())
            
        except Exception as e:
            logger.error(f"⚠️ Failed to initialize cost engine: {e}")
            # Start with zeros if can't load
            self._daily_spend = 0.0
            self._last_reset = date.today()
            self._dirty = False

    async def record_gpu_runtime(self, minutes: float) -> float:
        """Record GPU runtime and update cost"""
        hours = minutes / 60
        cost = hours * self.gpu_cost_per_hour

        self._daily_spend += cost
        self._dirty = True

        # Update metrics
        daily_gpu_cost.set(self._daily_spend)

        logger.info(f"💰 Recorded {minutes:.1f}min GPU runtime → +${cost:.4f} (total: ${self._daily_spend:.4f})")
        
        # Sync immediately if cost is significant (>$0.10)
        if cost > 0.10:
            await self._sync_to_rgw()
            
        return cost

    async def get_today_gpu_cost(self) -> float:
        """Get current day's GPU spend"""
        if self._last_reset != date.today():
            logger.info(f"📅 Day changed from {self._last_reset} to {date.today()}")
            self._daily_spend = 0.0
            self._last_reset = date.today()
            self._dirty = True
            await self._sync_to_rgw()

        return self._daily_spend

    async def can_use_gpu(self, estimated_cost: float = 0.0) -> bool:
        """Check if we can use GPU within budget"""
        current_spend = await self.get_today_gpu_cost()

        if current_spend >= self.daily_budget:
            logger.info(f"🚫 Budget exceeded: ${current_spend:.4f} >= ${self.daily_budget}")
            return False

        if current_spend + estimated_cost > self.daily_budget:
            logger.info(f"🚫 This request would exceed budget")
            return False

        remaining = self.daily_budget - current_spend
        if remaining < 0.50:
            logger.info(f"⚠️ Low budget: ${remaining:.2f} remaining - conserving GPU")
            return False

        return True

    async def estimate_query_cost(self, estimated_tokens: int) -> float:
        """Estimate cost for a GPU query"""
        cost_per_1k_tokens = 0.002
        return (estimated_tokens / 1000) * cost_per_1k_tokens

    async def close(self):
        """Clean shutdown - sync final state"""
        if self._dirty:
            await self._sync_to_rgw()
        if self._client:
            await self._client.__aexit__(None, None, None)

# Singleton instance
cost_engine = CostEngine()
