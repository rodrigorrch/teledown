from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any

@dataclass
class IndexedContent:
    id: int
    title: Optional[str]
    text: str
    date: datetime
    indexed_by: Optional[str]
    size: Optional[str]
    duration: Optional[str]
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IndexedContent':
        return cls(
            id=data['id'],
            title=data.get('title'),
            text=data['text'],
            date=datetime.fromisoformat(data['date']),
            indexed_by=data.get('indexed_by'),
            size=data.get('size'),
            duration=data.get('duration')
        )