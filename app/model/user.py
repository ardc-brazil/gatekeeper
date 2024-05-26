from dataclasses import dataclass


@dataclass
class UserProvider:
    name: str
    reference: str


@dataclass
class User:
    id: str = None
    name: str = None
    email: str = None
    providers: list[UserProvider] = None
    tenancies: list[str] = None
    roles: list[str] = None
    is_enabled: bool = True
    created_at: str = None
    updated_at: str = None


@dataclass
class UserQuery:
    email: str | None = None
    is_enabled: bool | None = True
