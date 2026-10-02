from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.exception.forbidden import ForbiddenException
from app.model.dataset_access import AccessLevel, DatasetAction
from app.model.db.dataset_access import DatasetAccessEvent
from app.model.sharing import ShareUser
from app.repository.access_event import AccessEventRepository
from app.repository.dataset_anonymous_link import DatasetAnonymousLinkRepository
from app.repository.dataset_invitation import DatasetInvitationRepository
from app.repository.user import UserRepository
from app.service.dataset import DatasetService

HISTORY_LIMIT = 100


@dataclass
class AccessHistoryEntry:
    event_type: str
    occurred_at: datetime
    actor: ShareUser | None
    subject: str | None
    old_value: dict | None
    new_value: dict | None
    note: str | None


class AccessHistoryService:
    def __init__(
        self,
        dataset_service: DatasetService,
        event_repository: AccessEventRepository,
        user_repository: UserRepository,
        invitation_repository: DatasetInvitationRepository,
        anonymous_link_repository: DatasetAnonymousLinkRepository,
    ) -> None:
        self._datasets = dataset_service
        self._events = event_repository
        self._users = user_repository
        self._invitations = invitation_repository
        self._links = anonymous_link_repository

    def _user(
        self, user_id: UUID | str | None, cache: dict[UUID, ShareUser | None]
    ) -> ShareUser | None:
        if not user_id:
            return None
        user_id = UUID(str(user_id))
        if user_id in cache:
            return cache[user_id]
        user = self._users.fetch_by_id(id=user_id, is_enabled=True) or (
            self._users.fetch_by_id(id=user_id, is_enabled=False)
        )
        resolved = (
            ShareUser(id=user.id, name=user.name, email=user.email) if user else None
        )
        cache[user_id] = resolved
        return resolved

    def _subject(
        self,
        dataset_id: UUID,
        event: DatasetAccessEvent,
        cache: dict[UUID, ShareUser | None],
    ) -> str | None:
        values = event.new_value or event.old_value or {}
        if "user_id" in values:
            user = self._user(values["user_id"], cache)
            return user.name if user else None
        if "link_id" in values:
            if values.get("label"):
                return values["label"]
            link = self._links.fetch(dataset_id, UUID(values["link_id"]))
            return link.label if link else None
        if "invitation_id" in values:
            invitation = self._invitations.fetch(
                dataset_id, UUID(values["invitation_id"])
            )
            if invitation is None:
                return None
            if invitation.email:
                return invitation.email
            if invitation.orcid:
                return f"ORCID {invitation.orcid}"
            return None
        return None

    def list(
        self, dataset_id: UUID, user_id: UUID, tenancies: list[str] | None
    ) -> list[AccessHistoryEntry]:
        dataset, _, level = self._datasets.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            action=DatasetAction.READ_METADATA,
        )
        if level not in (AccessLevel.OWNER, AccessLevel.WRITE):
            raise ForbiddenException(
                f"forbidden: access-history on {dataset_id} for {user_id}"
            )
        cache: dict[UUID, ShareUser | None] = {}
        return [
            AccessHistoryEntry(
                event_type=event.event_type,
                occurred_at=event.occurred_at,
                actor=self._user(event.changed_by, cache),
                subject=self._subject(dataset.id, event, cache),
                old_value=event.old_value,
                new_value=event.new_value,
                note=event.note,
            )
            for event in self._events.list_for_dataset(dataset.id, limit=HISTORY_LIMIT)
        ]
