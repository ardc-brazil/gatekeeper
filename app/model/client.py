from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class Client:
    name: str
    secret: str
    key: UUID = None
    is_enabled: bool = None
    created_at: datetime = None
    updated_at: datetime = None
