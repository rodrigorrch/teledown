from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

class CacheRepository(ABC):
    @abstractmethod
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached data by key"""
        pass
        
    @abstractmethod
    def set(self, key: str, data: Dict[str, Any]) -> None:
        """Save data to cache"""
        pass
        
    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete data from cache"""
        pass
        
    @abstractmethod
    def clear(self) -> None:
        """Clear all cached data"""
        pass