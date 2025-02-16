from dataclasses import dataclass
from pathlib import Path
from typing import Tuple, Optional
from ..entities.indexed_content import IndexedContent
from ..repositories.telegram_repository import TelegramRepository
from ...infrastructure.persistence.download_state import DownloadStateManager

@dataclass
class DownloadContentUseCase:
    telegram_repo: TelegramRepository
    download_manager: DownloadStateManager
    download_dir: Path
    
    async def download(self, content: IndexedContent) -> Tuple[bool, str]:
        """Download content and track its state"""
        if self.download_manager.is_downloaded(content.id):
            existing_path = self.download_manager.get_download_path(content.id)
            if Path(existing_path).exists():
                return True, f"Already downloaded: {existing_path}"
                
        # Create filename from content title or ID
        filename = self._generate_filename(content)
        file_path = self.download_dir / filename
        
        # Ensure download directory exists
        self.download_dir.mkdir(exist_ok=True)
        
        # Attempt download
        success = await self.telegram_repo.download_content(content, str(file_path))
        if success:
            self.download_manager.mark_downloaded(content.id, str(file_path))
            return True, str(file_path)
        
        return False, "Download failed"
        
    def _generate_filename(self, content: IndexedContent) -> str:
        """Generate a clean filename from content"""
        if content.title:
            # Clean up title for filename
            clean_title = "".join(c for c in content.title if c.isalnum() or c in " -_")
            return f"{content.id}_{clean_title[:50]}.mp4"
        return f"{content.id}.mp4"