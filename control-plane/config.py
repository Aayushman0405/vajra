from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # API - THIS MUST MATCH THE ENV VAR NAME
    api_key: str = "vajra-local-dev-key"  # Will be overridden by VAJRA_API_KEY env var

    # Cache
    qdrant_host: str = "qdrant.vajra-system.svc.cluster.local"
    qdrant_port: int = 6333
    qdrant_collection: str = "vajra-cache"
    
    # Cache settings - ADD THESE
    cache_threshold: float = 0.95
    cache_ttl_code: int = 1800      # 30 min
    cache_ttl_factual: int = 43200   # 12 hrs
    cache_ttl_creative: int = 300    # 5 min
    cache_max_entries: int = 1000    # ADD THIS
    cache_cleanup_interval: int = 3600  # ADD THIS

    # Models
    cpu_model: str = "phi-3-mini-4k-instruct"
    cpu_model_endpoint: str = "http://vajra-cpu-model.vajra-system.svc.cluster.local:8000/v1/chat/completions"
    gpu_model: str = "meta-llama/Llama-3-8b-instruct"
    embedding_model: str = "all-MiniLM-L6-v2"

    # AWS
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    aws_gpu_instance_type: str = "g4dn.xlarge"
    aws_gpu_ami: str = "ami-0a8b4cd6c7c9a7b9a"
    aws_key_name: str = "vajra-key"
    aws_security_group_id: str = ""
    aws_subnet_id: str = ""
    aws_ecr_repository: str = ""
    hf_token: str = ""

    # Cost
    daily_budget: float = 5.00
    aws_gpu_cost_per_hour: float = 0.526

    # RGW Configuration
    rgw_endpoint: str = ""
    rgw_access_key: str = ""
    rgw_secret_key: str = ""
    rgw_bucket: str = "vajra-cost-tracking"
    rgw_region: str = "us-east-1"
    rgw_path_style: bool = True

    class Config:
        env_file = ".env"
        env_prefix = "VAJRA_"


@lru_cache()
def get_settings():
    return Settings()


settings = get_settings()
