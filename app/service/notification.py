import logging
import math
from datetime import datetime, timedelta
from uuid import UUID

from app.logging_config import fields
from app.model.dataset_access import AccessEventType
from app.model.embargo import REMINDER_OFFSETS_DAYS
from app.repository.dataset_anonymous_link import DatasetAnonymousLinkRepository
from app.repository.embargo_notification import EmbargoNotificationRepository
from app.repository.permission import PermissionRepository
from app.repository.user import UserRepository
from app.service.dataset_access_audit import DatasetAccessAudit
from app.service.email import EmailService
from app.service.email_format import long_date, short_date, tenancy_display_name

MANUAL_DOI_NOTE = "manual DOI"


def _current_doi(dataset) -> tuple[str | None, bool]:
    versions = [
        version
        for version in (getattr(dataset, "versions", None) or [])
        if getattr(version, "doi", None) is not None
    ]
    if not versions:
        return None, False
    doi = max(versions, key=lambda version: version.created_at).doi
    state = (doi.state or "").rsplit(".", 1)[-1].upper()
    return doi.identifier, state == "REGISTERED"


def due_offset(
    until: datetime, set_at: datetime | None, now: datetime, offsets: tuple[int, ...]
) -> int | None:
    due = [
        offset
        for offset in offsets
        if until - timedelta(days=offset) <= now
        and (set_at is None or until - timedelta(days=offset) >= set_at)
    ]
    return min(due) if due else None


class EmbargoNotificationService:
    def __init__(
        self,
        notification_repository: EmbargoNotificationRepository,
        permission_repository: PermissionRepository,
        user_repository: UserRepository,
        anonymous_link_repository: DatasetAnonymousLinkRepository,
        audit: DatasetAccessAudit,
        email_service: EmailService,
        public_base_url: str,
    ) -> None:
        self._repository = notification_repository
        self._permissions = permission_repository
        self._users = user_repository
        self._links = anonymous_link_repository
        self._audit = audit
        self._email = email_service
        self._base_url = public_base_url.rstrip("/")
        self._logger = logging.getLogger("service:EmbargoNotificationService")

    def queue_due(self, now: datetime) -> int:
        queued = 0
        horizon = timedelta(days=max(REMINDER_OFFSETS_DAYS))
        for dataset in self._repository.datasets_with_reminders_due(now, horizon):
            try:
                set_at = self._repository.embargo_set_at(
                    dataset.id, dataset.embargo_until
                )
                offset = due_offset(
                    dataset.embargo_until, set_at, now, REMINDER_OFFSETS_DAYS
                )
                if offset is not None:
                    queued += self._queue_for_people(
                        dataset, "embargo_reminder", offset, now=now
                    )
            except Exception:
                self._logger.exception(
                    "embargo reminder pass failed",
                    extra=fields(dataset_id=str(dataset.id), **{"pass": "reminders"}),
                )
        for dataset in self._repository.datasets_expired_unannounced(now):
            try:
                ending = self._repository.ending_event(dataset.id)
                queued += self._queue_for_people(
                    dataset, "embargo_ended", None, now=now, ending=ending
                )
                self._audit.record(
                    dataset_id=dataset.id,
                    event_type=AccessEventType.EXPIRED,
                    changed_by=None,
                    new_value={"embargo_until": dataset.embargo_until.isoformat()},
                )
            except Exception:
                self._logger.exception(
                    "embargo ended pass failed",
                    extra=fields(dataset_id=str(dataset.id), **{"pass": "ended"}),
                )
        return queued

    def _any_user(self, user_id: UUID | None):
        if user_id is None:
            return None
        return self._users.fetch_by_id(
            id=user_id, is_enabled=True
        ) or self._users.fetch_by_id(id=user_id, is_enabled=False)

    def _people(
        self, dataset
    ) -> tuple[object | None, bool, list[tuple[object, UUID | None]]]:
        owner = self._any_user(dataset.owner_id)
        owner_active = owner is not None and bool(owner.is_enabled)
        holders = []
        for permission in self._permissions.list_for_dataset(dataset.id):
            user = self._users.fetch_by_id(id=permission.user_id, is_enabled=True)
            if user is not None:
                holders.append((user, getattr(permission, "granted_by", None)))
        return owner, owner_active, holders

    def _queue_for_people(
        self,
        dataset,
        template: str,
        offset: int | None,
        now: datetime,
        ending=None,
    ) -> int:
        owner, owner_active, holders = self._people(dataset)
        owner_name = owner.name if owner is not None and owner.name else "the owner"
        recipients = ([(owner, None)] if owner_active else []) + holders
        until = dataset.embargo_until.isoformat()
        base = {
            "dataset_name": dataset.name,
            "tenancy_name": tenancy_display_name(dataset.tenancy),
            "owner_name": owner_name,
            "owner_email": owner.email if owner is not None and owner_active else None,
            "anonymous_link_count": self._links.count_active(dataset.id),
            "dataset_url": f"{self._base_url}/app/datasets/{dataset.id}",
        }
        if template == "embargo_reminder":
            days_remaining = max(
                1, math.ceil((dataset.embargo_until - now) / timedelta(days=1))
            )
            base.update(
                days_remaining=days_remaining,
                embargo_until_date=long_date(dataset.embargo_until),
                embargo_until_short=short_date(dataset.embargo_until),
                later_offsets=sorted(
                    (later for later in REMINDER_OFFSETS_DAYS if later < offset),
                    reverse=True,
                ),
                owner_active=owner_active,
            )
        else:
            doi, doi_registered = _current_doi(dataset)
            base.update(
                ended_on_date=long_date(dataset.embargo_until),
                doi=doi,
                doi_registered=doi_registered,
                ended_early=ending is not None,
                ended_by_manual_doi=ending is not None
                and (ending.note or "") == MANUAL_DOI_NOTE,
            )
        queued = 0
        for person, granted_by in recipients:
            if not person.email:
                continue
            is_owner = owner_active and person.id == owner.id
            context = dict(base, is_owner=is_owner)
            if not is_owner:
                sharer = self._any_user(granted_by)
                context["shared_by_name"] = (
                    sharer.name if sharer is not None and sharer.name else owner_name
                )
            if template == "embargo_reminder":
                context.update(
                    can_extend=is_owner or not owner_active,
                    people_with_access=["You"] + [user.name for user, _ in holders]
                    if is_owner
                    else [],
                    others_notified=is_owner and bool(holders),
                )
                dedup_key = (
                    f"embargo_reminder:{dataset.id}:{until}:{offset}:{person.id}"
                )
            else:
                dedup_key = f"embargo_ended:{dataset.id}:{until}:{person.id}"
            queued += self._enqueue(
                template, person.email, context, dataset.id, dedup_key
            )
        return queued

    def _enqueue(
        self,
        template: str,
        recipient: str,
        context: dict,
        dataset_id: UUID,
        dedup_key: str,
    ) -> int:
        try:
            message_id = self._email.enqueue(
                template=template,
                recipient=recipient,
                context=context,
                related_type="dataset",
                related_id=dataset_id,
                dedup_key=dedup_key,
            )
        except Exception:
            self._logger.error(
                "email enqueue failed",
                exc_info=True,
                extra=fields(template=template, dataset_id=str(dataset_id)),
            )
            return 0
        return 1 if message_id is not None else 0
