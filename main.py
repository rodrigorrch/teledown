import os
import json
import sys
import signal
import asyncio
import redis
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from telethon import TelegramClient, errors
from telethon.tl.types import (
    MessageMediaDocument, 
    DocumentAttributeVideo,
    MessageMediaWebPage,
    Channel, 
    Message,
    Chat,
    MessageEntityUrl,
    MessageEntityTextUrl
)
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest

from rich.console import Console
from rich.prompt import Prompt
from tqdm import tqdm
from dotenv import load_dotenv

from download_manager import DownloadManager
from cache_manager import CacheManager

# Initialize console
console = Console()

# Load environment variables
load_dotenv()

# Get Telegram API credentials
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')

if not API_ID or not API_HASH:
    console.print("[red]Error: API_ID and API_HASH must be set in .env file[/red]")
    sys.exit(1)

class TeleDown:
    def __init__(self):
        self.client = TelegramClient('session/telethon', API_ID, API_HASH)
        self.download_manager = DownloadManager()
        self.cache_manager = CacheManager(cache_dir="cache")
        self.redis = None
        
        # Ensure directories exist
        os.makedirs("cache", exist_ok=True)
        os.makedirs("session", exist_ok=True)
        
    async def connect_redis(self, max_attempts=30):
        """Try to connect to Redis with retries"""
        attempt = 0
        while attempt < max_attempts:
            try:
                console.print(f"[yellow]Connecting to Redis (attempt {attempt + 1}/{max_attempts})...[/yellow]")
                self.redis = redis.Redis(host='redis', port=6379, db=0, socket_connect_timeout=5)
                self.redis.ping()  # Test connection
                console.print("[green]Connected to Redis![/green]")
                return True
            except Exception as e:
                attempt += 1
                if attempt < max_attempts:
                    wait_time = min(2 ** attempt, 30)  # Cap at 30 seconds
                    console.print(f"[yellow]Redis connection failed, retrying in {wait_time} seconds...[/yellow]")
                    await asyncio.sleep(wait_time)
                else:
                    console.print(f"[yellow]Warning: Redis connection failed after {max_attempts} attempts.[/yellow]")
                    self.redis = None
                    return False
        
    async def start(self):
        """Start the Telegram client and handle authentication"""
        # First try to connect to Redis
        await self.connect_redis()
        
        # Then start Telegram client
        await self.client.start()
        
        if not await self.client.is_user_authorized():
            # Try to get phone from Redis first
            if self.redis:
                try:
                    stored_phone = self.redis.get('user_phone')
                    if stored_phone:
                        phone = stored_phone.decode('utf-8')
                        console.print(f"[blue]Using stored phone number: {phone}[/blue]")
                except Exception:
                    phone = None
            
            if not phone:
                phone = Prompt.ask("[bold]Please enter your phone number[/bold] (with country code)")
                if self.redis:
                    try:
                        self.redis.set('user_phone', phone)
                    except Exception:
                        pass
            
            try:
                await self.client.send_code_request(phone)
                code = Prompt.ask("[bold]Please enter the code you received[/bold]")
                await self.client.sign_in(phone, code)
                console.print("[green]Successfully logged in![/green]")
            except Exception as e:
                console.print(f"[red]Login failed: {str(e)}[/red]")
                if self.redis:
                    try:
                        self.redis.delete('user_phone')  # Clear stored phone on error
                    except Exception:
                        pass
                raise
    
    async def get_channel_messages(self, channel_url):
        try:
            channel = await self._get_channel(channel_url)
            if not channel:
                console.print("[red]Não foi possível acessar o canal[/red]")
                return []

            # If we got here, we have access to the channel
            messages = []
            console.print(f"[yellow]Buscando mensagens do canal...[/yellow]")
            
            try:
                async for message in self.client.iter_messages(channel, limit=500):
                    if isinstance(message, Message):  # Ensure we only process valid Message objects
                        messages.append(message)
            except Exception as e:
                console.print(f"[red]Erro ao buscar mensagens: {str(e)}[/red]")
                return []

            total_messages = len(messages)
            console.print(f"Total de mensagens encontradas: {total_messages}")

            if total_messages == 0:
                console.print("[yellow]Nenhuma mensagem encontrada no canal[/yellow]")
                return []

            # First try to find indexed content
            indexed_content = []
            
            # Process messages for indexed content
            for msg in messages:
                if not isinstance(msg, Message) or not msg.message:
                    continue
                    
                content_info = self._extract_indexed_content(msg)
                if content_info:
                    indexed_content.append(content_info)

            # Try to get pinned messages
            try:
                pinned_messages = []
                
                # Try different methods to get pinned messages
                try:
                    # First try: Search for common pin emojis and keywords
                    pin_searches = ['📌', '📍', 'fixado', 'pinned']
                    for search_term in pin_searches:
                        async for message in self.client.iter_messages(channel, search=search_term, limit=10):
                            if message and message.message and message not in pinned_messages:
                                pinned_messages.append(message)
                except:
                    pass
                
                # Second try: Check recent messages
                if not pinned_messages:
                    async for message in self.client.iter_messages(channel, limit=30):
                        try:
                            if not message or not message.message:
                                continue
                                
                            msg_lower = message.message.lower()
                            
                            # Check for common pin indicators in the first line
                            first_line = msg_lower.split('\n')[0]
                            if any(indicator in first_line for indicator in 
                                ['📌', '📍', 'fixado', 'pinned', 'pin:', 'fixo', 'importante', 'important']):
                                pinned_messages.append(message)
                                
                        except Exception:
                            continue
                
                if pinned_messages:
                    console.print(f"\n[blue]Encontradas {len(pinned_messages)} mensagens importantes[/blue]")
                    for msg in pinned_messages:
                        if msg.message:
                            # Get the first line for display
                            first_line = msg.message.split('\n')[0]
                            console.print(f"[cyan]Mensagem: {first_line}[/cyan]")
                            
                            # Extract and process content
                            content_info = self._extract_indexed_content(msg)
                            if content_info:
                                indexed_content.append(content_info)
                else:
                    console.print("[yellow]Nenhuma mensagem importante encontrada[/yellow]")
                                
            except Exception as e:
                console.print(f"[red]Erro ao verificar mensagens importantes: {str(e)}[/red]")
                
            # Get channel description if available
            try:
                if hasattr(channel, 'about') and channel.about:
                    # Process description for indexed content
                    desc_msg = type('Message', (), {
                        'message': channel.about,
                        'id': 0,
                        'date': datetime.now(),
                        'entities': []
                    })
                    content_info = self._extract_indexed_content(desc_msg)
                    if content_info:
                        indexed_content.append(content_info)
            except Exception as e:
                console.print(f"[red]Erro ao processar descrição do canal: {str(e)}[/red]")

            # Display found content with improved list view
            if indexed_content:
                console.print("\n[green]═══════ Conteúdo Encontrado ═══════[/green]")
                
                # Track available downloads
                available_downloads = []
                
                # Show items in list format
                for i, info in enumerate(indexed_content, 1):
                    # Format title/name
                    title = info.get('title', 'Sem título')
                    title = title[:60] + '...' if len(title) > 60 else title
                    
                    # Format metadata
                    meta = []
                    if info.get('size'):
                        meta.append(f"📦 {info['size']}")
                    if info.get('duration'):
                        meta.append(f"⏱️ {info['duration']}")
                    if info.get('indexed_by'):
                        meta.append(f"📑 @{info['indexed_by']}")
                    
                    metadata = " | ".join(meta) if meta else ""
                    
                    # Check download status
                    msg_id = info.get('id')
                    download_status = ""
                    if msg_id:
                        for msg in messages:
                            if msg.id == msg_id and msg.media:
                                is_downloaded = self.download_manager.is_downloaded(msg.id)
                                if is_downloaded:
                                    download_status = "[blue]↺[/blue]"
                                else:
                                    download_status = "[green]↓[/green]"
                                available_downloads.append((i, msg, title, is_downloaded))
                                break
                    
                    # Print item in list format
                    console.print(f"{download_status} [{i}] {title}")
                    if metadata:
                        console.print(f"    {metadata}")
                
                # If we have available downloads, show download options
                if available_downloads:
                    console.print("\n[bold white]═══════ Downloads ═══════[/bold white]")
                    console.print("[yellow]Opções de download:[/yellow]")
                    console.print("• Número específico: [cyan]1[/cyan]")
                    console.print("• Lista de números: [cyan]1,3,5[/cyan]")
                    console.print("• Intervalo: [cyan]1-4[/cyan]")
                    console.print("• Sair: [cyan]0[/cyan]")
                    console.print("\n[dim]↓ = Novo | ↺ = Disponível para re-download[/dim]")
                    
                    while True:
                        choice = Prompt.ask(
                            "\n[bold]O que deseja baixar?[/bold]",
                            default="0"
                        )
                        
                        if choice.lower() == "0":
                            break
                            
                        try:
                            # Handle ranges like "1-3" or comma-separated numbers "1,2,3"
                            if "-" in choice:
                                start, end = map(int, choice.split("-"))
                                to_download = [i for i, _, _, _ in available_downloads if start <= i <= end]
                            elif "," in choice:
                                to_download = [int(x.strip()) for x in choice.split(",")]
                            else:
                                to_download = [int(choice)]
                                
                            # Download selected items
                            for item_num in to_download:
                                for i, msg, title, is_downloaded in available_downloads:
                                    if i == item_num:
                                        # If already downloaded, confirm re-download
                                        if is_downloaded:
                                            if not Prompt.ask(
                                                f"Item {i} já foi baixado. Deseja baixar novamente?", 
                                                choices=["s", "n"], 
                                                default="n"
                                            ) == "s":
                                                continue
                                        
                                        # Use title in filename if available
                                        filename = None
                                        if title:
                                            # Clean up title for filename
                                            clean_title = "".join(c for c in title if c.isalnum() or c in " -_")
                                            filename = f"{msg.id}_{clean_title[:50]}.mp4"
                                            
                                        success, result = await self.download_manager.download_media(
                                            self.client, msg, filename=filename
                                        )
                                        if success:
                                            console.print(f"[green]✓ Download concluído: {result}[/green]")
                                        else:
                                            console.print(f"[red]Erro ao baixar: {result}[/red]")
                            
                            # Ask if want to download more
                            if not Prompt.ask("Deseja baixar mais?", choices=["s", "n"], default="n") == "s":
                                break
                                
                        except ValueError:
                            console.print("[red]Entrada inválida. Use números, ranges (1-3) ou listas (1,2,3)[/red]")
                            continue
                    
            else:
                console.print("[yellow]Nenhum conteúdo indexado encontrado.[/yellow]")

            return indexed_content

        except Exception as e:
            console.print(f"[red]Erro ao acessar o canal: {str(e)}[/red]")
            return []

    async def _get_channel(self, channel_url):
        """Helper method to get and cache channel information"""
        try:
            # Check for different types of channel URLs
            if '+' in channel_url or 'joinchat' in channel_url:
                # Extract invite hash from different URL formats
                invite_hash = None
                if '/+' in channel_url:
                    invite_hash = channel_url.split('/+')[-1].split('/')[0].strip()
                elif '/joinchat/' in channel_url:
                    invite_hash = channel_url.split('/joinchat/')[-1].split('/')[0].strip()
                
                if not invite_hash:
                    console.print("[red]Link de convite inválido[/red]")
                    return None
                    
                console.print(f"\n[yellow]Tentando acessar canal privado com convite...[/yellow]")
                
                try:
                    # First try to get channel if already a member
                    try:
                        channel = await self.client.get_entity(channel_url)
                        console.print("[green]✓ Canal já acessado anteriormente![/green]")
                        return channel
                    except:
                        pass
                        
                    # Try to join using invite
                    updates = await self.client(ImportChatInviteRequest(invite_hash))
                    if updates and hasattr(updates, 'chats') and updates.chats:
                        channel = updates.chats[0]
                        console.print("[green]✓ Canal acessado com sucesso![/green]")
                        return channel
                        
                except Exception as e:
                    error_msg = str(e).upper()
                    if "FLOOD" in error_msg:
                        console.print("[yellow]Muitas tentativas. Aguarde alguns minutos e tente novamente.[/yellow]")
                    elif "INVITE_HASH_EXPIRED" in error_msg:
                        console.print("[red]Link de convite expirado[/red]")
                    elif "INVITE_REQUEST_SENT" in error_msg:
                        console.print("[yellow]Solicitação de entrada enviada. Aguarde aprovação.[/yellow]")
                    else:
                        console.print(f"[red]Erro ao entrar no canal: {str(e)}[/red]")
                    return None
                    
            else:
                # Handle regular channel username/URL
                channel_id = channel_url.split('/')[-1].replace('@', '').strip()
                if not channel_id:
                    console.print("[red]Username ou URL do canal inválido[/red]")
                    return None
                    
                console.print(f"\n[yellow]Buscando canal: @{channel_id}[/yellow]")
                
                try:
                    # Try to get channel directly first
                    channel = await self.client.get_entity(f"@{channel_id}")
                except ValueError:
                    try:
                        # Try joining if not found
                        await self.client(JoinChannelRequest(f"@{channel_id}"))
                        channel = await self.client.get_entity(f"@{channel_id}")
                    except Exception as e:
                        if "CHANNEL_PRIVATE" in str(e):
                            console.print("[red]Este é um canal privado. É necessário um link de convite.[/red]")
                        elif "CHANNEL_INVALID" in str(e):
                            console.print("[red]Canal não encontrado. Verifique o username ou URL.[/red]")
                        else:
                            console.print(f"[red]Erro ao acessar canal: {str(e)}[/red]")
                        return None

            if not isinstance(channel, (Channel, Chat)):
                console.print("[red]Entidade encontrada não é um canal ou grupo válido[/red]")
                return None

            # Display channel info
            console.print("\n[cyan]══════ Informações do Canal ══════[/cyan]")
            console.print(f"[bold white]Nome:[/bold white] {channel.title}")
            console.print(f"[bold white]Username:[/bold white] {'@' + channel.username if channel.username else '[italic]Canal Privado[/italic]'}")
            console.print(f"[bold white]ID:[/bold white] {channel.id}")
            console.print(f"[bold white]Tipo:[/bold white] {'Canal' if isinstance(channel, Channel) else 'Grupo'}")
            if hasattr(channel, 'participants_count') and channel.participants_count:
                console.print(f"[bold white]Membros:[/bold white] {channel.participants_count:,}")
            if hasattr(channel, 'about') and channel.about:
                console.print(f"[bold white]Descrição:[/bold white] {channel.about}")
            
            return channel

        except Exception as e:
            console.print(f"[red]Erro ao acessar canal: {str(e)}[/red]")
            return None

    def _extract_indexed_content(self, message):
        """Extract indexed content information from a message"""
        try:
            if not message or not hasattr(message, 'message') or not message.message:
                return None

            # Ensure message content is a string
            msg_text = str(message.message)
            msg_lower = msg_text.lower()
            msg_lines = [line for line in msg_text.split('\n') if line and isinstance(line, str)]

            if not msg_lines:
                return None

            content_info = None

            # Get message date safely
            msg_date = getattr(message, 'date', datetime.now()).strftime('%Y-%m-%d %H:%M:%S') if hasattr(message, 'date') else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Basic message info
            base_info = {
                'text': msg_text,
                'id': getattr(message, 'id', 0),
                'date': msg_date
            }

            # Look for indexing patterns first
            indexing_patterns = [
                r'(?:indexado\s+por|indexed\s+by)\s*@?(\w+)',
                r'(?:disponível\s+em|available\s+at)\s*@?(\w+)',
                r'(?:acesse|veja\s+em)\s*@?(\w+)',
                r'(?:conteúdo\s+em|content\s+at)\s*@?(\w+)',
                r'@?(\w+).*(?:indexou|indexado|indexed)',
                r'(?:canal(?:\s+oficial)?|channel)\s*[:-]?\s*@?(\w+)',
                r'(?:grupo|group)\s*[:-]?\s*@?(\w+)',
                r'fonte|source\s*[:-]?\s*@?(\w+)'
            ]

            # Look for metadata patterns
            size_pattern = r'(?:tamanho|size):\s*(\d+(?:\.\d+)?)\s*(gb|mb|tb)'
            duration_pattern = r'(?:duração|duration):\s*(\d+)\s*h\s*(?:(\d+)\s*min)?'
            
            # Initialize content with base info if we find relevant information
            for line in msg_lines:
                if not isinstance(line, str):
                    continue
                    
                line = line.strip()
                if not line:
                    continue
                    
                line_lower = line.lower()
                
                # Check for indexing references
                for pattern in indexing_patterns:
                    indexing_match = re.search(pattern, line, re.IGNORECASE)
                    if indexing_match and indexing_match.group(1):
                        username = indexing_match.group(1).strip('@')
                        # Ignore common false positives
                        if username.lower() not in ['telegram', 'me', 'bot', 'share']:
                            if not content_info:
                                content_info = base_info.copy()
                                content_info['indexed_by'] = username
                            break

                # Look for size information
                size_match = re.search(size_pattern, line_lower)
                if size_match and size_match.group(1) and size_match.group(2):
                    if not content_info:
                        content_info = base_info.copy()
                    try:
                        size_num = float(size_match.group(1))
                        size_unit = size_match.group(2).lower()
                        content_info['size'] = f"{size_num} {size_unit}"
                    except (ValueError, TypeError):
                        pass
                
                # Look for duration information
                duration_match = re.search(duration_pattern, line_lower)
                if duration_match and duration_match.group(1):
                    if not content_info:
                        content_info = base_info.copy()
                    try:
                        hours = int(duration_match.group(1))
                        minutes = int(duration_match.group(2)) if duration_match.group(2) else 0
                        content_info['duration'] = f"{hours}h {minutes}min"
                    except (ValueError, TypeError):
                        pass
                
                # Try to identify a title from the first non-empty line
                # that's not a metadata line
                if not content_info:
                    if not any(keyword in line_lower 
                           for keyword in ['tamanho:', 'size:', 'duração:', 'duration:', 'indexado', 'indexed']):
                        content_info = base_info.copy()
                        content_info['title'] = line

            return content_info

        except Exception as e:
            console.print(f"[red]Erro ao processar mensagem: {str(e)}[/red]")
            return None

def signal_handler(sig, frame):
    """Handle termination signals"""
    console.print("\n[yellow]Shutting down gracefully...[/yellow]")
    # Force exit since we're in a container
    os._exit(0)

async def main():
    try:
        # Set up signal handlers for container environment
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGHUP, signal_handler)
        
        teledown = TeleDown()
        await teledown.start()
        console.print("[green]Connected to Telegram![/green]")
        
        while True:
            try:
                sys.stdout.write("\nEnter channel URL or @username (or 'exit' to quit): ")
                sys.stdout.flush()
                
                channel_url = sys.stdin.readline()
                if not channel_url:  # EOF received
                    break
                    
                channel_url = channel_url.strip()
                if not channel_url:  # Empty input
                    continue
                    
                if channel_url.lower() == 'exit':
                    break
                    
                await teledown.get_channel_messages(channel_url)
                
            except (EOFError, KeyboardInterrupt):
                break
            except Exception as e:
                console.print(f"[red]Error: {str(e)}[/red]")
                continue
                
    except Exception as e:
        console.print(f"[red]Fatal error: {str(e)}[/red]")
    finally:
        if hasattr(teledown, 'client'):
            await teledown.client.disconnect()
        console.print("[yellow]Disconnected from Telegram[/yellow]")
        # Ensure clean exit in container
        os._exit(0)

if __name__ == "__main__":
    try:
        # Set event loop policy for better Windows compatibility
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        # Create and run event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(main())
        except KeyboardInterrupt:
            console.print("\n[yellow]Program terminated by user[/yellow]")
        except Exception as e:
            console.print(f"[red]Fatal error: {str(e)}[/red]")
        finally:
            try:
                loop.close()
            except:
                pass
            # Ensure clean exit
            os._exit(0)
            
    except Exception as e:
        console.print(f"[red]Event loop error: {str(e)}[/red]")
        sys.exit(1)