from dataclasses import dataclass


@dataclass
class UserProvider:
    name: str
    reference: str


@dataclass
class User:
    id: str
    name: str
    email: str
    is_enabled: bool
    created_at: str
    updated_at: str
    providers: list[UserProvider]
    tenancies: list[str]
    roles: list[str]


@dataclass
class UserQuery:
    email: str | None = None
    is_enabled: bool | None = True
