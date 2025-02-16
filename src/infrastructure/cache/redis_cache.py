from pathlib import Path
import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import redis

from ...domain.repositories.cache_repository import CacheRepository

class RedisCacheRepository(CacheRepository):
    def __init__(self, host: str = None, port: int = None, db: int = 0, ttl_hours: int = 3):
        self.redis = redis.Redis(
            host=host or os.getenv('REDIS_HOST', 'redis'),
            port=port or int(os.getenv('REDIS_PORT', 6379)),
            db=db,
            decode_responses=True
        )
        self.ttl = timedelta(hours=ttl_hours)
        
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        try:
            data = self.redis.get(key)
            if data:
                return json.loads(data)
        except Exception:
            pass
        return None
        
    def set(self, key: str, data: Dict[str, Any]) -> None:
        try:
            json_data = json.dumps(data)
            self.redis.set(key, json_data, ex=int(self.ttl.total_seconds()))
        except Exception:
            pass
            
    def delete(self, key: str) -> None:
        try:
            self.redis.delete(key)
        except Exception:
            pass
            
    def clear(self) -> None:
        try:
            self.redis.flushdb()
        except Exception:
            pass