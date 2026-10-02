from datetime import datetime, timezone
from typing import Callable, Iterable
from uuid import UUID

from app.exception.bad_request import BadRequestException, ErrorDetails
from app.exception.not_found import NotFoundException
from app.metrics import metrics
from app.model.dataset import VisibilityStatus
from app.model.dataset_access import AccessEventType, DatasetAction
from app.model.db.dataset import DataFile
from app.model.db.dataset import Dataset as DatasetDBModel
from app.model.db.sharing import DatasetAnonymousLink
from app.model.embargo import embargo_active
from app.model.sharing import (
    AnonymousExtension,
    AnonymousLinkView,
    AnonymousPage,
    AnonymousVersion,
)
from app.repository.dataset import DatasetRepository
from app.repository.dataset_anonymous_link import DatasetAnonymousLinkRepository
from app.service.dataset import DatasetService
from app.service.dataset_access_audit import DatasetAccessAudit
from app.service.redaction import redact_metadata
from app.service.share_token import hash_token, new_token, token_hint


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _spelled(extension: str | None) -> str | None:
    stripped = (extension or "").strip().lstrip(".").lower()
    return f".{stripped}" if stripped else None


def _extensions(files: Iterable[DataFile]) -> list[AnonymousExtension]:
    grouped: dict[str | None, list[int]] = {}
    for file in files:
        grouped.setdefault(_spelled(file.extension), []).append(file.size_bytes or 0)
    return sorted(
        (
            AnonymousExtension(
                extension=extension, count=len(sizes), total_size_bytes=sum(sizes)
            )
            for extension, sizes in grouped.items()
        ),
        key=lambda item: item.total_size_bytes,
        reverse=True,
    )


class AnonymousLinkService:
    def __init__(
        self,
        dataset_service: DatasetService,
        anonymous_link_repository: DatasetAnonymousLinkRepository,
        dataset_repository: DatasetRepository,
        audit: DatasetAccessAudit,
        public_base_url: str,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._dataset_service = dataset_service
        self._links = anonymous_link_repository
        self._datasets = dataset_repository
        self._audit = audit
        self._base_url = public_base_url.rstrip("/")
        self._clock = clock

    def _authorized(self, dataset_id: UUID, user_id: UUID) -> DatasetDBModel:
        dataset, _, _ = self._dataset_service.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=None,
            action=DatasetAction.WRITE,
        )
        return dataset

    def create(
        self, dataset_id: UUID, user_id: UUID, label: str
    ) -> tuple[AnonymousLinkView, str]:
        dataset = self._authorized(dataset_id, user_id)
        if not embargo_active(dataset.embargo_until, self._clock()):
            raise BadRequestException(errors=[ErrorDetails(code="embargo_not_active")])

        token = new_token()
        link = self._links.create(
            DatasetAnonymousLink(
                dataset_id=dataset.id,
                token_hash=hash_token(token),
                token_hint=token_hint(token),
                label=label.strip(),
                created_by=user_id,
            )
        )
        self._audit.record(
            dataset_id=dataset.id,
            event_type=AccessEventType.ANONYMOUS_LINK_CREATED,
            changed_by=user_id,
            new_value={"link_id": str(link.id), "label": link.label},
        )
        metrics.anonymous_link_created(dataset.tenancy)
        view = AnonymousLinkView(
            id=link.id,
            label=link.label,
            created_at=link.created_at,
            revoked_at=None,
            token_hint=link.token_hint,
        )
        return view, f"{self._base_url}/anonymous/{token}"

    def revoke(self, dataset_id: UUID, user_id: UUID, link_id: UUID) -> None:
        dataset = self._authorized(dataset_id, user_id)
        link = self._links.fetch(dataset.id, link_id)
        if link is None or link.revoked_at is not None:
            raise NotFoundException(f"not_found: {link_id}")
        if not self._links.revoke(link_id, self._clock()):
            raise NotFoundException(f"not_found: {link_id}")
        self._audit.record(
            dataset_id=dataset.id,
            event_type=AccessEventType.ANONYMOUS_LINK_REVOKED,
            changed_by=user_id,
            old_value={"link_id": str(link_id)},
        )

    def view(self, token: str) -> AnonymousPage:
        link = self._links.fetch_by_token_hash(hash_token(token))
        dataset = None
        if link is not None and link.revoked_at is None:
            dataset = self._datasets.fetch(
                dataset_id=link.dataset_id, restrict_by_tenancy=False
            )
        if dataset is None:
            metrics.anonymous_link_viewed(None, "not_found")
            raise NotFoundException("anonymous_link_not_found")

        if embargo_active(dataset.embargo_until, self._clock()):
            state, outcome = "active", "shown"
        elif dataset.visibility == VisibilityStatus.PUBLIC:
            self._links.record_view(link.id, "redirected")
            metrics.anonymous_link_viewed(dataset.tenancy, "redirected")
            return AnonymousPage(state="published", dataset_id=dataset.id)
        else:
            state, outcome = "ended", "shown_after_embargo"

        self._links.record_view(link.id, outcome)
        metrics.anonymous_link_viewed(dataset.tenancy, outcome)
        return AnonymousPage(
            state=state,
            dataset_id=dataset.id,
            embargo_until=dataset.embargo_until if state == "active" else None,
            embargo_ended_at=dataset.embargo_until if state == "ended" else None,
            name=dataset.name,
            data=redact_metadata(dataset.data),
            versions=[
                AnonymousVersion(
                    name=version.name,
                    created_at=version.created_at,
                    file_count=len(version.files_in),
                    total_size_bytes=sum(
                        file.size_bytes or 0 for file in version.files_in
                    ),
                    extensions=_extensions(version.files_in),
                )
                for version in dataset.versions
                if version.is_enabled
            ],
        )
