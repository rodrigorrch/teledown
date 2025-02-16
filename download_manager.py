import json
from pathlib import Path
from datetime import datetime
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

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
    
    async def download_media(self, client, message, filename=None):
        """Download media from a message"""
        try:
            if not message.media:
                return False, "Mensagem não contém mídia"
                
            # Get default filename if none provided
            if not filename:
                filename = f"{message.id}.mp4"
            
            filepath = self.downloads_dir / filename
            
            # Check if file exists and handle duplicates
            if filepath.exists():
                # Add number suffix if file exists
                counter = 1
                while filepath.exists():
                    name = filepath.stem
                    # Remove existing counter if any
                    if '_v' in name:
                        name = name.rsplit('_v', 1)[0]
                    new_filename = f"{name}_v{counter}{filepath.suffix}"
                    filepath = self.downloads_dir / new_filename
                    counter += 1
            
            # Create progress bar
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn()
            ) as progress:
                
                task = progress.add_task(f"[cyan]Baixando: {filepath.name}", total=100)
                
                # Download callback to update progress bar
                def callback(current, total):
                    progress.update(task, completed=int(current * 100 / total))
                
                # Download the file
                downloaded_file = await client.download_media(
                    message,
                    file=str(filepath),
                    progress_callback=callback
                )
            
            # Update download state
            self.state[str(message.id)] = {
                "status": "completed",
                "file": filepath.name,
                "date": datetime.now().isoformat(),
                "size": filepath.stat().st_size if filepath.exists() else 0
            }
            self._save_state(self.state)
            
            return True, str(filepath)
            
        except Exception as e:
            return False, f"Erro ao baixar: {str(e)}"
    
    def get_download_path(self, message_id):
        """Get the download path for a message"""
        if str(message_id) in self.state:
            info = self.state[str(message_id)]
            if info["status"] == "completed":
                filepath = self.downloads_dir / info["file"]
                if filepath.exists():
                    return filepath
        return None
        
    def get_download_info(self, message_id):
        """Get download information for a message"""
        if str(message_id) in self.state:
            return self.state[str(message_id)]
        return None