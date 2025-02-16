import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

class CacheManager:
    def __init__(self, cache_dir: str = "cache", ttl_hours: int = 8):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.channel_cache_file = self.cache_dir / "channels.json"
        self.ttl = timedelta(hours=ttl_hours)
        self.channels: Dict[str, Any] = self._load_channels()
        
    def _load_channels(self) -> Dict[str, Any]:
        """Load cached channels from file"""
        if self.channel_cache_file.exists():
            try:
                with open(self.channel_cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}
        
    def _save_channels(self):
        """Save channels to cache file"""
        try:
            with open(self.channel_cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.channels, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving channel cache: {e}")
            
    def get_channel(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """Get channel from cache if not expired"""
        if channel_id in self.channels:
            channel_data = self.channels[channel_id]
            # Check if cache is still valid using configured TTL
            cached_time = datetime.fromisoformat(channel_data['cached_at'])
            if datetime.now() - cached_time < self.ttl:
                return channel_data['data']
            else:
                # Remove expired cache
                del self.channels[channel_id]
                self._save_channels()
        return None
        
    def save_channel(self, channel_id: str, channel_data: Any):
        """Save channel data to cache"""
        self.channels[channel_id] = {
            'data': channel_data,
            'cached_at': datetime.now().isoformat()
        }
        self._save_channels()
        
    def clear_cache(self):
        """Clear all cached data"""
        self.channels.clear()
        self._save_channels()