from pathlib import Path
import json
from typing import Dict, Any, Set
from datetime import datetime

class DownloadStateManager:
    def __init__(self, downloads_dir: str = "downloads"):
        self.downloads_dir = Path(downloads_dir)
        self.state_file = self.downloads_dir / "state.json"
        self.downloads_dir.mkdir(exist_ok=True)
        self.state: Dict[str, Any] = self._load_state()
        
    def _load_state(self) -> Dict[str, Any]:
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}
        
    def _save_state(self):
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
            
    def mark_downloaded(self, content_id: int, file_path: str):
        self.state[str(content_id)] = {
            'file_path': str(file_path),
            'downloaded_at': datetime.now().isoformat()
        }
        self._save_state()
        
    def is_downloaded(self, content_id: int) -> bool:
        return str(content_id) in self.state
        
    def get_download_path(self, content_id: int) -> str:
        if self.is_downloaded(content_id):
            return self.state[str(content_id)]['file_path']
        return ""
        
    def get_downloaded_files(self) -> Set[Path]:
        return {Path(info['file_path']) 
                for info in self.state.values()}