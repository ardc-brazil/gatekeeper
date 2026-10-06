from typing import Any
from uuid import UUID

from app.model.tenancy_access import UserBrief, UserRef
from app.repository.user import UserRepository


def user_brief(users: UserRepository, user_id: UUID) -> UserBrief:
    user = users.fetch_any_by_id(user_id)
    if user is None:
        return UserBrief(id=user_id, name="Deleted account", email=None)
    return UserBrief(id=user.id, name=user.name, email=user.email)


def user_ref(users: UserRepository, user_id: UUID | None) -> UserRef | None:
    if user_id is None:
        return None
    user = users.fetch_any_by_id(user_id)
    return UserRef(id=user.id, name=user.name) if user else None


def orcid_of(user: Any) -> str | None:
    return next((p.reference for p in user.providers or [] if p.name == "orcid"), None)
