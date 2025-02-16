from abc import ABC, abstractmethod
from typing import Optional, List
from ..entities.channel import Channel
from ..entities.indexed_content import IndexedContent

class TelegramRepository(ABC):
    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to Telegram"""
        pass
        
    @abstractmethod
    async def get_channel(self, url_or_username: str) -> Optional[Channel]:
        """Get channel information"""
        pass
        
    @abstractmethod
    async def get_channel_messages(self, channel: Channel) -> List[IndexedContent]:
        """Get indexed content from channel messages"""
        pass
        
    @abstractmethod
    async def download_content(self, content: IndexedContent, file_path: str) -> bool:
        """Download media content"""
        pass