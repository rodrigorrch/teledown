from dataclasses import dataclass
from typing import Optional, List
from ..entities.channel import Channel
from ..entities.indexed_content import IndexedContent
from ..repositories.telegram_repository import TelegramRepository
from ..repositories.cache_repository import CacheRepository

@dataclass
class ChannelContentUseCase:
    telegram_repo: TelegramRepository
    cache_repo: CacheRepository
    
    async def get_channel_content(self, url_or_username: str) -> Optional[List[IndexedContent]]:
        """Get indexed content from a channel, using cache when available"""
        # Try to get from cache first
        cached_data = self.cache_repo.get(url_or_username)
        if cached_data:
            return [IndexedContent.from_dict(item) for item in cached_data.get('contents', [])]
            
        # If not in cache, fetch from Telegram
        channel = await self.telegram_repo.get_channel(url_or_username)
        if not channel:
            return None
            
        contents = await self.telegram_repo.get_channel_messages(channel)
        if contents:
            # Cache the results
            self.cache_repo.set(url_or_username, {
                'channel': channel.__dict__,
                'contents': [content.__dict__ for content in contents]
            })
            
        return contents