import os
import json
from datetime import datetime
from telethon import TelegramClient, errors
from telethon.tl.types import (
    MessageMediaDocument, 
    DocumentAttributeVideo,
    MessageMediaWebPage,
    WebPage,
    Channel, 
    User, 
    Message,
    Chat,
    MessageEntityUrl,
    MessageEntityTextUrl,
    InputPeerChannel,
    InputChannel
)
from telethon.tl.functions.messages import GetHistoryRequest, ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich import print as rprint
from tqdm import tqdm
from pathlib import Path
from download_manager import DownloadManager
from cache_manager import CacheManager
import re

console = Console()

# Telegram API credentials from environment variables
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')

class TeleDown:
    def __init__(self):
        self.client = TelegramClient('session/telethon', API_ID, API_HASH)
        self.download_manager = DownloadManager()
        self.cache_manager = CacheManager(cache_dir="cache")
        
        # Ensure cache directory exists
        os.makedirs("cache", exist_ok=True)
        
    async def start(self):
        await self.client.start()
        if not await self.client.is_user_authorized():
            phone = Prompt.ask("Please enter your phone number (with country code)")
            await self.client.send_code_request(phone)
            code = Prompt.ask("Please enter the code you received")
            await self.client.sign_in(phone, code)
    
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
                # Get pinned messages using search parameter
                pinned_messages = []
                async for msg in self.client.iter_messages(channel, search='', pinned=True):
                    if isinstance(msg, Message):
                        pinned_messages.append(msg)
                        
                if pinned_messages:
                    console.print(f"[blue]Encontradas {len(pinned_messages)} mensagens fixadas[/blue]")
                    for msg in pinned_messages:
                        if msg.message:
                            console.print(f"[cyan]Mensagem fixada: {msg.message[:100]}...[/cyan]")
                            content_info = self._extract_indexed_content(msg)
                            if content_info:
                                indexed_content.append(content_info)
                                
            except Exception as e:
                console.print(f"[red]Erro ao verificar mensagens fixadas: {str(e)}[/red]")

            # Display indexed content if found
            if indexed_content:
                console.print("\n[green]Conteúdo indexado encontrado:[/green]")
                for info in indexed_content:
                    console.print("\n[cyan]" + "-" * 50 + "[/cyan]")
                    if info.get('title'):
                        console.print(f"[bold]{info['title']}[/bold]")
                    if info.get('size'):
                        console.print(f"[yellow]Tamanho: {info['size']}[/yellow]")
                    if info.get('duration'):
                        console.print(f"[yellow]Duração: {info['duration']}[/yellow]")
                    if info.get('indexed_by'):
                        console.print(f"[yellow]Indexado por: @{info['indexed_by']}[/yellow]")
                    if info.get('text'):
                        console.print(f"\n{info['text']}")
            else:
                console.print("[yellow]Nenhum conteúdo indexado encontrado.[/yellow]")

            # Process messages for media content
            processed_messages = []
            with console.status(f"[yellow]Processando {total_messages} mensagens...") as status:
                for i, message in enumerate(messages):
                    if not isinstance(message, Message):
                        continue
                        
                    status.update(f"[yellow]Processando mensagens... {i+1}/{total_messages} ({((i+1)/total_messages*100):.1f}%)")
                    
                    try:
                        media_info = self._process_message_media(message)
                        if media_info:
                            processed_messages.append(media_info)
                            type_str = f" [{media_info['type']}]" if media_info.get('type') else ""
                            console.print(f"[green]✓ Conteúdo encontrado{type_str}: {media_info['title']}[/green]")
                    except Exception as e:
                        console.print(f"[red]Erro ao processar mensagem {message.id}: {str(e)}[/red]")
                        continue

            return sorted(processed_messages, key=lambda x: x['date'], reverse=True)

        except Exception as e:
            console.print(f"[red]Erro ao processar canal: {str(e)}[/red]")
            return []

    async def _get_channel(self, channel_url):
        """Helper method to get and cache channel information"""
        try:
            # For private channels with invite links
            if 't.me/+' in channel_url or 't.me/joinchat/' in channel_url:
                # Extract invite hash from URL format
                invite_hash = None
                if '/+' in channel_url:
                    invite_hash = channel_url.split('/+')[-1].split('/')[0].strip()
                elif '/joinchat/' in channel_url:
                    invite_hash = channel_url.split('/joinchat/')[-1].split('/')[0].strip()

                if not invite_hash:
                    console.print("[red]Link de convite inválido[/red]")
                    return None

                console.print(f"[yellow]Tentando acessar canal privado com convite...[/yellow]")
                
                try:
                    # First try to get entity directly in case we're already a member
                    try:
                        channel = await self.client.get_entity(channel_url)
                        console.print("[green]✓ Canal já acessado anteriormente![/green]")
                        return channel
                    except:
                        pass

                    # If not already a member, try to join
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

            # For public channels
            else:
                # Remove any URL components and get just the username
                channel_id = channel_url.split('/')[-1].replace('@', '').strip()
                if channel_id.startswith('+'):
                    console.print("[red]Link de convite inválido. Use o formato completo t.me/+HASH[/red]")
                    return None
                    
                console.print(f"\n[yellow]Buscando canal: @{channel_id}[/yellow]")
                
                try:
                    channel = await self.client.get_entity(f"@{channel_id}")
                except ValueError:
                    try:
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
        """Helper method to extract indexed content information from a message"""
        if not message.message:
            return None
            
        msg_lines = message.message.split('\n')
        content_info = None
        
        # Check for message entities (URLs, mentions, etc)
        if message.entities:
            for entity in message.entities:
                if isinstance(entity, (MessageEntityUrl, MessageEntityTextUrl)):
                    url = entity.url if hasattr(entity, 'url') else message.message[entity.offset:entity.offset + entity.length]
                    if 't.me/' in url:
                        channel_username = url.split('t.me/')[-1].split('/')[0].strip()
                        if not content_info:
                            content_info = {
                                'text': message.message,
                                'indexed_by': channel_username.replace('@', '')
                            }

        for line in msg_lines:
            line_lower = line.lower()
            
            # Extended indexing patterns
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
            
            for pattern in indexing_patterns:
                indexing_match = re.search(pattern, line, re.IGNORECASE)
                if indexing_match and not content_info:
                    username = indexing_match.group(1).strip('@')
                    # Ignore common false positives
                    if username.lower() not in ['telegram', 'me', 'bot', 'share']:
                        content_info = {
                            'text': message.message,
                            'indexed_by': username
                        }
                        break
            
            # Look for size and duration info
            size_match = re.search(r'(?:tamanho|size):\s*(\d+(?:\.\d+)?)\s*(gb|mb|tb)', line_lower)
            duration_match = re.search(r'(?:duração|duration):\s*(\d+)\s*h\s*(?:(\d+)\s*min)?', line_lower)
            
            if size_match:
                if not content_info:
                    content_info = {'text': message.message}
                size_num = float(size_match.group(1))
                size_unit = size_match.group(2).lower()
                content_info['size'] = f"{size_num} {size_unit}"
            
            if duration_match:
                if not content_info:
                    content_info = {'text': message.message}
                hours = int(duration_match.group(1))
                minutes = int(duration_match.group(2)) if duration_match.group(2) else 0
                content_info['duration'] = f"{hours}h {minutes}min"
            
        return content_info if content_info and (content_info.get('indexed_by') or 
                                               (content_info.get('size') and content_info.get('duration'))) else None

    def _process_message_media(self, message):
        """Helper method to process media content from a message"""
        if not isinstance(message, Message):
            return None
            
        is_media = False
        media_url = None
        file_size = 0
        duration = None
        file_name = None
        media_type = None
        
        try:
            if message.media:
                if isinstance(message.media, MessageMediaDocument):
                    is_media = True
                    if hasattr(message.media.document, 'size'):
                        file_size = message.media.document.size
                    
                    for attr in message.media.document.attributes:
                        if hasattr(attr, 'file_name') and attr.file_name:
                            file_name = attr.file_name
                        if isinstance(attr, DocumentAttributeVideo):
                            duration = attr.duration
                            media_type = 'video'
                            break
                    
                    if hasattr(message.media.document, 'mime_type'):
                        mime = message.media.document.mime_type.lower()
                        if not media_type:  # Only set if not already set by attributes
                            if 'video' in mime:
                                media_type = 'video'
                            elif 'audio' in mime:
                                media_type = 'audio'
                            elif 'pdf' in mime:
                                media_type = 'pdf'
                            elif any(t in mime for t in ['zip', 'rar', 'x-compressed']):
                                media_type = 'archive'
                
                elif isinstance(message.media, MessageMediaWebPage) and message.media.webpage:
                    if message.media.webpage.url:
                        media_url = message.media.webpage.url
                        if any(domain in media_url.lower() for domain in [
                            'youtube.com', 'youtu.be', 'vimeo.com', 'drive.google.com',
                            'mega.nz', 'mediafire.com', 'dropbox.com'
                        ]):
                            is_media = True
                            media_type = 'external_link'

            if message.message:
                # Check for course content patterns
                if any(pattern in message.message.lower() for pattern in [
                    'módulo', 'aula', 'parte', 'class', 'curso', 'lição'
                ]):
                    is_media = True
                    if not media_type:
                        media_type = 'course_content'

            if is_media:
                title = message.message or file_name or f"Media {message.id}"
                title = title.split('\n')[0] if '\n' in title else title
                title = title[:100] + '...' if len(title) > 100 else title
                
                return {
                    'id': message.id,
                    'date': message.date.strftime('%Y-%m-%d %H:%M:%S'),
                    'title': title,
                    'size': file_size,
                    'duration': duration,
                    'url': media_url,
                    'file_name': file_name,
                    'type': media_type,
                    'downloaded': self.download_manager.is_downloaded(message.id),
                    'forwarded': bool(message.forward)
                }
        
        except Exception as e:
            console.print(f"[red]Erro ao processar mídia da mensagem {message.id}: {str(e)}[/red]")
        
        return None

    async def download_video(self, channel_url, message_id):
        try:
            message = await self.client.get_messages(channel_url, ids=message_id)
            if not message or not message.media:
                return False

            file_path = f"downloads/{message_id}.mp4"
            
            # ...existing code...
            # Create progress bar
            progress = tqdm(total=message.media.document.size, 
                          unit='B', unit_scale=True)

            # ...existing code...
            # Download callback
            async def callback(current, total):
                progress.n = current
                progress.refresh()

            await self.client.download_media(
                message,
                file=file_path,
                progress_callback=callback
            )
            progress.close()
            
            self.download_manager.mark_as_downloaded(message_id)
            return True
            
        except Exception as e:
            console.print(f"[red]Error downloading video {message_id}: {str(e)}[/red]")
            return False

    @staticmethod
    def format_size(size_bytes):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    @staticmethod
    def format_duration(seconds):
        if not seconds:
            return "N/A"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"

async def main():
    try:
        teledown = TeleDown()
        await teledown.start()

        channel_url = Prompt.ask("\nEnter channel URL or username")
        messages = await teledown.get_channel_messages(channel_url)

        if not messages:
            console.print("[yellow]No content found[/yellow]")
            return

        # ...existing code...
        # Group messages by type
        messages_by_type = {}
        for msg in messages:
            msg_type = msg.get('type', 'unknown')
            if msg_type not in messages_by_type:
                messages_by_type[msg_type] = []
            messages_by_type[msg_type].append(msg)

        # ...existing code...
        # Display content by type
        console.print("\n[bold cyan]Found content:[/bold cyan]")
        for content_type, type_messages in messages_by_type.items():
            console.print(f"\n[bold]{content_type.upper()}[/bold] ({len(type_messages)} items):")
            for msg in type_messages:
                status = "[green]✓[/green]" if msg['downloaded'] else "[yellow]□[/yellow]"
                size_str = TeleDown.format_size(msg['size']) if msg['size'] else "N/A"
                duration_str = TeleDown.format_duration(msg['duration']) if msg['duration'] else ""
                duration_display = f" - {duration_str}" if duration_str else ""
                url_display = f" [link]" if msg.get('url') else ""
                
                console.print(f"{status} [{msg['id']}] {msg['title']} ({size_str}{duration_display}){url_display}")
        
        # ...existing code...
        # Select content to download
        content_ids = Prompt.ask("\nEnter content IDs to download (comma-separated)")
        content_ids = [int(cid.strip()) for cid in content_ids.split(',') if cid.strip()]
        
        for content_id in content_ids:
            if not teledown.download_manager.is_downloaded(content_id):
                console.print(f"\n[yellow]Downloading content {content_id}...[/yellow]")
                success = await teledown.download_video(channel_url, content_id)
                if success:
                    console.print(f"[green]Successfully downloaded content {content_id}[/green]")
            else:
                console.print(f"[blue]Content {content_id} already downloaded[/blue]")
                
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())