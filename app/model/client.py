from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class Client:
    key: UUID = None
    name: str
    secret: str
    is_enabled: bool = None
    created_at: datetime = None
    updated_at: datetime = None
