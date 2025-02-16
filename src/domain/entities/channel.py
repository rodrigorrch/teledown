from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class Channel:
    id: int
    title: str
    username: Optional[str]
    is_private: bool
    members_count: Optional[int]
    description: Optional[str]
    joined_date: Optional[datetime] = None