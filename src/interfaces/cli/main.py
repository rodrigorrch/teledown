import os
import sys
import signal
import asyncio
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.prompt import Prompt
from dotenv import load_dotenv

from ...domain.usecases.get_channel_content import ChannelContentUseCase
from ...domain.usecases.download_content import DownloadContentUseCase
from ...infrastructure.telegram.telegram_client import TelegramClientImpl
from ...infrastructure.cache.redis_cache import RedisCacheRepository
from ...infrastructure.persistence.download_state import DownloadStateManager

class TeleDownCLI:
    def __init__(self):
        self.console = Console()
        self.downloads_dir = Path("downloads")
        self.session_dir = Path("session")
        
        # Ensure directories exist
        self.downloads_dir.mkdir(exist_ok=True)
        self.session_dir.mkdir(exist_ok=True)
        
        # Load environment variables
        load_dotenv()
        
        # Get Telegram API credentials
        self.api_id = os.getenv('API_ID')
        self.api_hash = os.getenv('API_HASH')
        
        if not self.api_id or not self.api_hash:
            self.console.print("[red]Error: API_ID and API_HASH must be set in .env file[/red]")
            sys.exit(1)
            
        # Initialize components
        self.telegram_client = TelegramClientImpl(self.api_id, self.api_hash, str(self.session_dir / "telethon"))
        self.cache_repo = RedisCacheRepository(ttl_hours=3)  # 3-hour TTL as requested
        self.download_manager = DownloadStateManager(str(self.downloads_dir))
        
        # Initialize use cases
        self.channel_content_usecase = ChannelContentUseCase(self.telegram_client, self.cache_repo)
        self.download_content_usecase = DownloadContentUseCase(
            self.telegram_client,
            self.download_manager,
            self.downloads_dir
        )
        
    async def start(self):
        """Start the CLI interface"""
        try:
            if not await self.telegram_client.connect():
                self.console.print("[red]Failed to connect to Telegram[/red]")
                return
                
            self.console.print("[green]Connected to Telegram![/green]")
            
            while True:
                try:
                    channel_url = Prompt.ask("\nEnter channel URL or @username (or 'exit' to quit)")
                    if channel_url.lower() == 'exit':
                        break
                        
                    await self._process_channel(channel_url)
                    
                except (EOFError, KeyboardInterrupt):
                    break
                except Exception as e:
                    self.console.print(f"[red]Error: {str(e)}[/red]")
                    
        finally:
            await self.telegram_client.client.disconnect()
            self.console.print("[yellow]Disconnected from Telegram[/yellow]")
            
    async def _process_channel(self, channel_url: str):
        """Process a channel URL and handle content download"""
        contents = await self.channel_content_usecase.get_channel_content(channel_url)
        if not contents:
            self.console.print("[red]No content found in channel[/red]")
            return
            
        self.console.print(f"\n[green]Found {len(contents)} indexed items[/green]")
        
        # Display content list
        for i, content in enumerate(contents, 1):
            title = content.title or f"Content {content.id}"
            meta = []
            if content.size:
                meta.append(f"📦 {content.size}")
            if content.duration:
                meta.append(f"⏱️ {content.duration}")
            if content.indexed_by:
                meta.append(f"📑 @{content.indexed_by}")
                
            status = "[blue]↺[/blue]" if self.download_manager.is_downloaded(content.id) else "[green]↓[/green]"
            self.console.print(f"{status} [{i}] {title}")
            if meta:
                self.console.print(f"    {' | '.join(meta)}")
                
        # Handle download selection
        while True:
            choice = Prompt.ask(
                "\n[bold]What would you like to download?[/bold] (number, range like 1-3, or comma-separated list)",
                default="0"
            )
            
            if choice == "0":
                break
                
            try:
                to_download = self._parse_download_choice(choice, len(contents))
                for idx in to_download:
                    content = contents[idx - 1]
                    if self.download_manager.is_downloaded(content.id):
                        if not Prompt.ask(
                            f"Content {idx} was already downloaded. Download again?",
                            choices=["y", "n"],
                            default="n"
                        ) == "y":
                            continue
                            
                    self.console.print(f"\n[yellow]Downloading {content.title or f'Content {content.id}'}...[/yellow]")
                    success, result = await self.download_content_usecase.download(content)
                    
                    if success:
                        self.console.print(f"[green]✓ Download complete: {result}[/green]")
                    else:
                        self.console.print(f"[red]✗ Download failed: {result}[/red]")
                        
                if not Prompt.ask("Download more?", choices=["y", "n"], default="n") == "y":
                    break
                    
            except ValueError as e:
                self.console.print(f"[red]Invalid input: {str(e)}[/red]")
                
    def _parse_download_choice(self, choice: str, max_items: int) -> list[int]:
        """Parse user's download choice into a list of indices"""
        indices = set()
        
        for part in choice.split(','):
            if '-' in part:
                start, end = map(str.strip, part.split('-'))
                start = int(start)
                end = int(end)
                if not (1 <= start <= end <= max_items):
                    raise ValueError(f"Range {start}-{end} is invalid")
                indices.update(range(start, end + 1))
            else:
                idx = int(part.strip())
                if not (1 <= idx <= max_items):
                    raise ValueError(f"Index {idx} is out of range")
                indices.add(idx)
                
        return sorted(indices)
                
def main():
    """Entry point for the CLI application"""
    cli = TeleDownCLI()
    
    def signal_handler(sig, frame):
        """Handle termination signals"""
        cli.console.print("\n[yellow]Shutting down gracefully...[/yellow]")
        sys.exit(0)
        
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Set up event loop
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        loop = asyncio.get_event_loop()
        loop.run_until_complete(cli.start())
    except Exception as e:
        cli.console.print(f"[red]Fatal error: {str(e)}[/red]")
    finally:
        try:
            loop.close()
        except:
            pass