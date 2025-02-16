import os
import re
from datetime import datetime
from typing import Optional, List, Dict, Any
from telethon import TelegramClient, errors
from telethon.tl.types import Channel as TelethonChannel, Chat, Message
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest

from ...domain.repositories.telegram_repository import TelegramRepository
from ...domain.entities.channel import Channel
from ...domain.entities.indexed_content import IndexedContent
from rich.console import Console

class TelegramClientImpl(TelegramRepository):
    def __init__(self, api_id: str, api_hash: str, session_path: str = 'session/telethon'):
        self.client = TelegramClient(session_path, api_id, api_hash)
        self.console = Console()
        
    async def connect(self) -> bool:
        await self.client.start()
        return await self.client.is_user_authorized()
        
    async def get_channel(self, url_or_username: str) -> Optional[Channel]:
        try:
            entity = None
            
            # Handle private channel links
            if '+' in url_or_username or 'joinchat' in url_or_username:
                invite_hash = None
                if '/+' in url_or_username:
                    invite_hash = url_or_username.split('/+')[-1].split('/')[0].strip()
                elif '/joinchat/' in url_or_username:
                    invite_hash = url_or_username.split('/joinchat/')[-1].split('/')[0].strip()
                
                if invite_hash:
                    try:
                        # First check if we can get info about the invite
                        invite = await self.client(CheckChatInviteRequest(invite_hash))
                        if hasattr(invite, 'chat'):
                            entity = invite.chat
                        else:
                            # Try to join if not already in the channel
                            updates = await self.client(ImportChatInviteRequest(invite_hash))
                            if updates and hasattr(updates, 'chats') and updates.chats:
                                entity = updates.chats[0]
                    except errors.UserAlreadyParticipantError:
                        # If we're already in the channel, get it by its ID
                        if hasattr(invite, 'chat'):
                            entity = invite.chat
                    except Exception as e:
                        self.console.print(f"[red]Error joining private channel: {str(e)}[/red]")
            
            # Handle public channels
            if not entity:
                channel_id = url_or_username.split('/')[-1].replace('@', '').strip()
                try:
                    entity = await self.client.get_entity(f"@{channel_id}")
                except ValueError:
                    try:
                        await self.client(JoinChannelRequest(f"@{channel_id}"))
                        entity = await self.client.get_entity(f"@{channel_id}")
                    except Exception as e:
                        self.console.print(f"[red]Error joining public channel: {str(e)}[/red]")
                        return None
            
            if isinstance(entity, (TelethonChannel, Chat)):
                return Channel(
                    id=entity.id,
                    title=entity.title,
                    username=getattr(entity, 'username', None),
                    is_private=not bool(getattr(entity, 'username', None)),
                    members_count=getattr(entity, 'participants_count', None),
                    description=getattr(entity, 'about', None),
                    joined_date=datetime.now()
                )
                
            return None
            
        except Exception as e:
            self.console.print(f"[red]Error getting channel: {str(e)}[/red]")
            return None
            
    async def get_channel_messages(self, channel: Channel) -> List[IndexedContent]:
        """Get indexed content from channel messages"""
        indexed_contents = []
        
        try:
            # Increase limit and add progress feedback
            self.console.print("[yellow]Fetching messages from channel...[/yellow]")
            message_count = 0
            
            async for message in self.client.iter_messages(channel.id, limit=1000):
                message_count += 1
                if message_count % 100 == 0:
                    self.console.print(f"[yellow]Processed {message_count} messages...[/yellow]")
                    
                try:
                    if isinstance(message, Message):
                        content_info = self._extract_indexed_content(message)
                        if content_info:
                            indexed_contents.append(content_info)
                except Exception as e:
                    self.console.print(f"[red]Error processing message {message.id}: {str(e)}[/red]")
                    continue
                    
            self.console.print(f"[green]Found {len(indexed_contents)} indexed items from {message_count} messages[/green]")
            
        except Exception as e:
            self.console.print(f"[red]Error getting channel messages: {str(e)}[/red]")
            
        return indexed_contents
        
    async def download_content(self, content: IndexedContent, file_path: str) -> bool:
        try:
            message = await self.client.get_messages(content.id)
            if message and message.media:
                await self.client.download_media(message, file_path)
                return True
        except Exception:
            pass
        return False
        
    def _extract_indexed_content(self, message: Message) -> Optional[IndexedContent]:
        """Extract indexed content information from a message"""
        try:
            if not message:
                return None

            # First check if message has media since we only want media messages
            if not hasattr(message, 'media') or not message.media:
                return None

            msg_text = str(message.message) if message.message else ""
            msg_lower = msg_text.lower()
            msg_lines = [line.strip() for line in msg_text.split('\n') if line and isinstance(line, str)]

            # Basic message info
            base_info = {
                'text': msg_text,
                'id': message.id,
                'date': message.date.isoformat(),
                'title': None,
                'indexed_by': None,
                'size': None,
                'duration': None
            }

            # Enhanced metadata patterns
            size_patterns = [
                r'(?:tamanho|size|tam)(?:\s*)?[:-]?\s*(\d+(?:\.\d+)?)\s*(gb|mb|tb)',
                r'(\d+(?:\.\d+)?)\s*(gb|mb|tb)',
                r'size\s*[-:]?\s*(\d+(?:\.\d+)?)\s*(gb|mb|tb)'
            ]
            
            duration_patterns = [
                r'(?:duração|duration|dur)(?:\s*)?[:-]?\s*(\d+)\s*h\s*(?:(\d+)\s*min)?',
                r'(\d+)\s*h(?:oras?)?\s*(?:(\d+)\s*min(?:utos?)?)?',
                r'(\d+):(\d+)(?::00)?'  # HH:MM format
            ]

            indexing_patterns = [
                r'(?:indexado\s+por|indexed\s+by)\s*@?(\w+)',
                r'(?:disponível\s+em|available\s+at)\s*@?(\w+)',
                r'(?:acesse|veja\s+em)\s*@?(\w+)',
                r'(?:conteúdo\s+em|content\s+at)\s*@?(\w+)',
                r'@?(\w+).*(?:indexou|indexado|indexed)',
                r'(?:canal(?:\s+oficial)?|channel)\s*[:-]?\s*@?(\w+)',
                r'(?:grupo|group)\s*[:-]?\s*@?(\w+)',
                r'fonte|source\s*[:-]?\s*@?(\w+)',
                r'@(\w+)',  # Simple @ mention as last resort
                r'(?:by|por)\s+@?(\w+)'  # Generic by/por attribution
            ]
            
            # Try to identify title - use first non-empty line by default
            for line in msg_lines:
                line_lower = line.lower()
                # Skip lines that look like metadata
                if any(p in line_lower for p in ['tamanho', 'size', 'duração', 'duration', 'indexado', 'indexed', '@']):
                    continue
                base_info['title'] = line
                break

            # Look for size information
            for pattern in size_patterns:
                size_match = re.search(pattern, msg_lower)
                if size_match and size_match.group(1) and size_match.group(2):
                    try:
                        size_num = float(size_match.group(1))
                        size_unit = size_match.group(2).lower()
                        base_info['size'] = f"{size_num} {size_unit}"
                        break
                    except (ValueError, TypeError):
                        continue

            # Look for duration information
            for pattern in duration_patterns:
                duration_match = re.search(pattern, msg_lower)
                if duration_match:
                    try:
                        if ':' in pattern:  # HH:MM format
                            hours = int(duration_match.group(1))
                            minutes = int(duration_match.group(2))
                        else:  # Nh MMmin format
                            hours = int(duration_match.group(1))
                            minutes = int(duration_match.group(2)) if duration_match.group(2) else 0
                        base_info['duration'] = f"{hours}h {minutes}min"
                        break
                    except (ValueError, TypeError):
                        continue

            # Check for indexing references
            for pattern in indexing_patterns:
                for line in msg_lines:
                    match = re.search(pattern, line, re.IGNORECASE)
                    if match and match.group(1):
                        username = match.group(1).strip('@')
                        # Ignore common false positives
                        if username.lower() not in ['telegram', 'me', 'bot', 'share']:
                            base_info['indexed_by'] = username
                            break
                if base_info['indexed_by']:
                    break

            # Always return content if it has media, even if we couldn't extract all metadata
            return IndexedContent.from_dict(base_info)

        except Exception as e:
            self.console.print(f"[red]Error extracting content: {str(e)}[/red]")
            return None