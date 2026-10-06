from dataclasses import dataclass
from datetime import datetime

DEFAULT_ROLE = "datasets_write"
ADMIN_ROLE = "admin"


def is_admin(roles: list[str] | None) -> bool:
    return ADMIN_ROLE in (roles or [])


@dataclass
class UserProvider:
    name: str
    reference: str


@dataclass
class User:
    id: str = None
    name: str = None
    email: str | None = None
    providers: list[UserProvider] = None
    tenancies: list[str] = None
    roles: list[str] = None
    is_enabled: bool = True
    created_at: str = None
    updated_at: str = None
    email_verified_at: datetime | None = None
    has_password: bool = False


@dataclass
class UserQuery:
    email: str | None = None
    is_enabled: bool | None = True
