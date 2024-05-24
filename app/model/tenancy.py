from dataclasses import dataclass
from datetime import datetime


@dataclass
class Tenancy:
    name: str
    is_enabled: bool = True
    created_at: datetime = None
    updated_at: datetime = None
