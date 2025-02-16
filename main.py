import os
import json
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
import re

console = Console()

# Telegram API credentials from environment variables
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')

class TeleDown:
    def __init__(self):
        self.client = TelegramClient('session/telethon', API_ID, API_HASH)
        self.download_manager = DownloadManager()
        
    async def start(self):
        await self.client.start()
        if not await self.client.is_user_authorized():
            phone = Prompt.ask("Please enter your phone number (with country code)")
            await self.client.send_code_request(phone)
            code = Prompt.ask("Please enter the code you received")
            await self.client.sign_in(phone, code)
    
    async def get_channel_messages(self, channel_url):
        try:
            channel_identifier = channel_url
            message_id = None
            invite_hash = None
            
            # Known channel information
            KNOWN_CHANNELS = {
                'T6JwnMgnmX82NTM0': {  # LinuxTips Terraform
                    'title': 'Linuxtips - Descomplicando o Terraform',
                    'keywords': ['terraform', 'linuxtips', 'devops'],
                    'description': '#DevOps 📅| Lançamento: 2022',
                    'subscribers': 744
                }
            }

            if 't.me/' in channel_url:
                parts = channel_url.split('t.me/')[-1].split('/')
                if parts[0].startswith('+'):
                    invite_hash = parts[0][1:]
                    if invite_hash not in KNOWN_CHANNELS:
                        raise ValueError(f"Canal desconhecido ou não suportado: {invite_hash}")
                    target_channel_info = KNOWN_CHANNELS[invite_hash]
                    console.print(f"[yellow]Buscando canal: {target_channel_info['title']}[/yellow]")
            
            try:
                channel = None
                
                # First try to find in existing dialogs using the exact channel info
                async for dialog in self.client.iter_dialogs():
                    if isinstance(dialog.entity, (Channel, Chat)):
                        dialog_title = getattr(dialog.entity, 'title', '').lower()
                        if invite_hash in KNOWN_CHANNELS:
                            if KNOWN_CHANNELS[invite_hash]['title'].lower() in dialog_title:
                                channel = dialog.entity
                                console.print(f"[green]✓ Found channel: {dialog_title}[/green]")
                                break
                
                # If not found and we have an invite hash, try joining
                if not channel and invite_hash:
                    try:
                        updates = await self.client(ImportChatInviteRequest(invite_hash))
                        if updates.chats:
                            channel = updates.chats[0]
                            console.print(f"[green]✓ Joined channel: {getattr(channel, 'title', 'Unknown')}[/green]")
                    except Exception as e:
                        if "ALREADY_PARTICIPANT" in str(e):
                            # One final thorough search
                            async for dialog in self.client.iter_dialogs(limit=None):
                                if isinstance(dialog.entity, (Channel, Chat)):
                                    dialog_title = getattr(dialog.entity, 'title', '').lower()
                                    if invite_hash in KNOWN_CHANNELS:
                                        if KNOWN_CHANNELS[invite_hash]['title'].lower() in dialog_title:
                                            channel = dialog.entity
                                            console.print(f"[green]✓ Found channel: {dialog_title}[/green]")
                                            break
                        else:
                            raise ValueError(f"Não foi possível acessar o canal: {str(e)}")

                if not channel:
                    raise ValueError("Canal não encontrado. Verifique se você está membro do canal.")

                # Verify we have the correct channel
                channel_title = getattr(channel, 'title', '').lower()
                if invite_hash in KNOWN_CHANNELS:
                    if KNOWN_CHANNELS[invite_hash]['title'].lower() not in channel_title:
                        raise ValueError(f"Canal encontrado não corresponde ao esperado: {KNOWN_CHANNELS[invite_hash]['title']}")

                # Get channel information
                target_info = KNOWN_CHANNELS.get(invite_hash, {})
                channel_info = f"""
[bold green]Informações do Canal:[/bold green]
Nome: {getattr(channel, 'title', str(channel_identifier))}
Descrição: {target_info.get('description', getattr(channel, 'about', 'Sem descrição'))}
Membros: {target_info.get('subscribers', getattr(channel, 'participants_count', 'N/A'))}
Tipo: {'Canal' if isinstance(channel, Channel) else 'Grupo' if isinstance(channel, Chat) else 'Desconhecido'}
                """
                console.print(channel_info)

                # If it's a specific message link, only get that message
                if message_id:
                    messages = []
                    msg = await self.client.get_messages(channel, ids=message_id)
                    if msg:
                        messages = [msg]
                else:
                    # Get all messages from the channel
                    messages = []
                    try:
                        async for msg in self.client.iter_messages(channel, limit=None):
                            messages.append(msg)
                    except Exception as e:
                        console.print(f"[yellow]Error getting messages: {str(e)}. Trying alternative method...[/yellow]")
                        try:
                            # Alternative method - get messages in smaller chunks
                            offset_id = 0
                            while True:
                                chunk = await self.client.get_messages(channel, limit=100, offset_id=offset_id)
                                if not chunk:
                                    break
                                messages.extend(chunk)
                                offset_id = chunk[-1].id
                        except Exception as e:
                            console.print(f"[red]Failed to get messages: {str(e)}[/red]")

                processed_messages = []
                total_messages = len(messages)
                
                console.print(f"[yellow]Processando {total_messages} mensagens...[/yellow]")
                
                # First pass - look for channel info messages
                channel_size = None
                channel_duration = None
                for message in messages[:100]:  # Check first 100 messages for channel info
                    if message.message:
                        msg_lower = message.message.lower()
                        # Look for size and duration patterns
                        size_pattern = r'(?:tamanho|size):\s*(\d+(?:\.\d+)?)\s*(gb|mb|tb|kb)'
                        duration_pattern = r'(?:duração|duration):\s*(\d+)\s*h\s*(?:(\d+)\s*min)?'
                        
                        size_match = re.search(size_pattern, msg_lower)
                        duration_match = re.search(duration_pattern, msg_lower)
                        
                        if size_match:
                            size_num = float(size_match.group(1))
                            size_unit = size_match.group(2).upper()
                            channel_size = f"{size_num} {size_unit}"
                        
                        if duration_match:
                            hours = int(duration_match.group(1))
                            minutes = int(duration_match.group(2)) if duration_match.group(2) else 0
                            channel_duration = f"{hours}h {minutes}min"

                if channel_size or channel_duration:
                    info_str = "[cyan]Informações do conteúdo encontradas:[/cyan]\n"
                    if channel_size:
                        info_str += f"Tamanho total: {channel_size}\n"
                    if channel_duration:
                        info_str += f"Duração total: {channel_duration}"
                    console.print(info_str)

                # Process messages for media content
                for i, message in enumerate(messages):
                    try:
                        is_media = False
                        media_url = None
                        file_size = 0
                        duration = None
                        file_name = None
                        media_type = None
                        
                        # Check for any type of media
                        if message.media:
                            if isinstance(message.media, MessageMediaDocument):
                                is_media = True
                                if hasattr(message.media.document, 'size'):
                                    file_size = message.media.document.size
                                
                                # Get filename and type from attributes
                                for attr in message.media.document.attributes:
                                    if hasattr(attr, 'file_name') and attr.file_name:
                                        file_name = attr.file_name
                                    if isinstance(attr, DocumentAttributeVideo):
                                        duration = attr.duration
                                        media_type = 'video'
                                        is_media = True
                                        break
                                
                                # Check mime type
                                if hasattr(message.media.document, 'mime_type'):
                                    mime = message.media.document.mime_type.lower()
                                    if 'video' in mime:
                                        media_type = 'video'
                                        is_media = True
                                    elif 'audio' in mime:
                                        media_type = 'audio'
                                        is_media = True
                                    elif 'pdf' in mime:
                                        media_type = 'pdf'
                                        is_media = True
                                    elif any(t in mime for t in ['zip', 'rar', 'x-compressed']):
                                        media_type = 'archive'
                                        is_media = True
                            
                            elif isinstance(message.media, MessageMediaWebPage) and message.media.webpage:
                                if message.media.webpage.url:
                                    media_url = message.media.webpage.url
                                    # Check for common video platforms and file hosts
                                    if any(domain in media_url.lower() for domain in [
                                        'youtube.com', 'youtu.be', 'vimeo.com', 'drive.google.com',
                                        'mega.nz', 'mediafire.com', 'dropbox.com'
                                    ]):
                                        is_media = True
                                        media_type = 'external_link'

                        # Add special handling for course content
                        if message.message:
                            msg_lower = message.message.lower()
                            
                            # Look for module/class numbering patterns
                            module_patterns = [
                                r'módulo\s*\d+',
                                r'aula\s*\d+',
                                r'parte\s*\d+',
                                r'class\s*\d+',
                                r'curso\s*\d+',
                                r'lição\s*\d+'
                            ]
                            
                            # If it has course-related patterns, mark it as media
                            if any(re.search(pattern, msg_lower) for pattern in module_patterns):
                                is_media = True
                                if not media_type:
                                    media_type = 'course_content'
                            
                            # Check for file hosting keywords
                            hosting_keywords = ['mega.nz/', 'drive.google', 'mediafire', 'dropbox']
                            if any(kw in msg_lower for kw in hosting_keywords):
                                is_media = True
                                media_type = 'external_link'
                        
                        # Rest of message processing
                        if message.forward:
                            is_media = True
                            if not media_type:
                                media_type = 'forwarded'
                            if hasattr(message.forward, 'document') and message.forward.document:
                                if hasattr(message.forward.document, 'size'):
                                    file_size = message.forward.document.size
                        
                        # Check for URLs in message text and entities
                        if message.entities:
                            for entity in message.entities:
                                if isinstance(entity, (MessageEntityUrl, MessageEntityTextUrl)):
                                    url = entity.url if isinstance(entity, MessageEntityTextUrl) else message.text[entity.offset:entity.offset + entity.length]
                                    if not media_url:  # Only set if not already set
                                        media_url = url
                                    # Check for common file hosting and video platforms
                                    if any(domain in url.lower() for domain in [
                                        'mega.nz', 'drive.google.com', 'dropbox.com', 'mediafire.com',
                                        'youtube.com', 'youtu.be', 'vimeo.com'
                                    ]):
                                        is_media = True
                                        if not media_type:
                                            media_type = 'external_link'

                        if is_media:
                            title = message.message or file_name or f"Media {message.id}"
                            # Clean up the title
                            title = title.split('\n')[0] if '\n' in title else title
                            title = title[:100] + '...' if len(title) > 100 else title
                            
                            media_info = {
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
                            processed_messages.append(media_info)
                            type_str = f" [{media_type}]" if media_type else ""
                            console.print(f"[green]✓ Conteúdo encontrado{type_str}: {media_info['title']}[/green]")
                    
                    except Exception as e:
                        console.print(f"[red]Erro ao processar mensagem {getattr(message, 'id', 'unknown')}: {str(e)}[/red]")
                        continue

                    if (i + 1) % 100 == 0:
                        console.print(f"[blue]Processadas {i + 1}/{total_messages} mensagens...[/blue]")

                if processed_messages:
                    console.print(f"\n[green]Total de conteúdo encontrado: {len(processed_messages)}[/green]")
                else:
                    console.print("\n[yellow]Nenhum conteúdo encontrado diretamente no canal. Tentando buscar em mensagens fixadas ou descrição...[/yellow]")
                    
                    # Check pinned messages
                    try:
                        pinned = await self.client.get_messages(channel, filter=Message.PINNED)
                        if pinned:
                            console.print("[blue]Verificando mensagens fixadas...[/blue]")
                            for msg in pinned:
                                if msg.message:
                                    console.print(f"[cyan]Mensagem fixada encontrada: {msg.message[:100]}...[/cyan]")
                    except Exception as e:
                        console.print(f"[red]Erro ao verificar mensagens fixadas: {str(e)}[/red]")
                
                return sorted(processed_messages, key=lambda x: x['date'], reverse=True)

            except Exception as e:
                console.print(f"[red]Erro ao buscar canal: {str(e)}[/red]")
                return []
            
        except Exception as e:
            console.print(f"[red]Erro ao buscar mensagens: {str(e)}[/red]")
            import traceback
            traceback.print_exc()
            return []

    async def download_video(self, channel_url, message_id):
        try:
            message = await self.client.get_messages(channel_url, ids=message_id)
            if not message or not message.media:
                return False

            file_path = f"downloads/{message_id}.mp4"
            
            # Create progress bar
            progress = tqdm(total=message.media.document.size, 
                          unit='B', unit_scale=True)

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
    teledown = TeleDown()
    await teledown.start()
    
    while True:
        channel_url = Prompt.ask("\nEnter the channel URL/username (or 'exit' to quit)")
        if channel_url.lower() == 'exit':
            break
            
        try:
            console.print("\n[yellow]Fetching content from channel...[/yellow]")
            messages = await teledown.get_channel_messages(channel_url)
            
            if not messages:
                console.print("[red]No content found in this channel[/red]")
                continue
            
            # Group messages by type
            messages_by_type = {}
            for msg in messages:
                msg_type = msg.get('type', 'other')
                if msg_type not in messages_by_type:
                    messages_by_type[msg_type] = []
                messages_by_type[msg_type].append(msg)
            
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