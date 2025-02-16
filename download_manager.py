import json
from pathlib import Path

class DownloadManager:
    def __init__(self):
        self.state_file = Path("downloads/state.json")
        self.downloads_dir = Path("downloads")
        self._init_directories()
        self.state = self._load_state()
    
    def _init_directories(self):
        """Initialize required directories"""
        self.downloads_dir.mkdir(exist_ok=True)
        Path("session").mkdir(exist_ok=True)
        
        if not self.state_file.exists():
            self._save_state({})
    
    def _load_state(self):
        """Load download state from file"""
        try:
            return json.loads(self.state_file.read_text())
        except:
            return {}
    
    def _save_state(self, state):
        """Save download state to file"""
        self.state_file.write_text(json.dumps(state, indent=2))
    
    def is_downloaded(self, message_id):
        """Check if a video has been downloaded"""
        return str(message_id) in self.state
    
    def mark_as_downloaded(self, message_id):
        """Mark a video as successfully downloaded"""
        self.state[str(message_id)] = {
            "status": "completed",
            "file": f"{message_id}.mp4"
        }
        self._save_state(self.state)
    
    def get_incomplete_downloads(self):
        """Get list of incomplete downloads"""
        return [
            int(msg_id) for msg_id, info in self.state.items()
            if info["status"] != "completed"
        ]