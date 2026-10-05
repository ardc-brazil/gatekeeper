import logging
from datetime import datetime, timezone
from typing import Callable
from uuid import UUID

from app.exception.bad_request import BadRequestException, ErrorDetails
from app.exception.conflict import ConflictException
from app.exception.not_found import NotFoundException
from app.logging_config import fields
from app.model.db.sharing import DatasetInvitation
from app.model.dataset_access import AccessEventType, DatasetAction, PermissionLevel
from app.model.sharing import (
    AcceptResult,
    GrantRequest,
    GrantResult,
    InvitationPreview,
    InvitationView,
    PermissionView,
    AnonymousLinkView,
    AnonymousLinkViews,
    ShareState,
    ShareUser,
    TenancyAccess,
)
from app.repository.dataset import DatasetRepository
from app.repository.dataset_invitation import DatasetInvitationRepository
from app.repository.dataset_anonymous_link import DatasetAnonymousLinkRepository
from app.repository.permission import PermissionRepository
from app.repository.user import UserRepository
from app.service.dataset import DatasetService
from app.service.dataset_access import allows_member_edits
from app.service.email import EmailService
from app.service.email_format import long_date
from app.service.email_template import EmailTemplate
from app.service.dataset_access_audit import DatasetAccessAudit
from app.service.permission import PermissionService
from app.service.share_identity import (
    find_account,
    normalise_email,
    normalise_orcid,
)
from app.service.share_token import hash_token, new_token
from app.service.user import UserService
from app.model.tenancy import is_default
from app.repository.tenancy import TenancyRepository
from app.service.tenancy_invitation import TenancyInvitationService
from app.service.tenancy_membership import TenancyMembershipService

PLACEHOLDER_EMAIL_DOMAIN = "@fake.mail.com"


def _bad(code: str) -> BadRequestException:
    return BadRequestException(errors=[ErrorDetails(code=code)])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def deliverable(email: str | None) -> bool:
    return bool(email) and not email.lower().endswith(PLACEHOLDER_EMAIL_DOMAIN)


class ShareService:
    def __init__(
        self,
        dataset_service: DatasetService,
        dataset_repository: DatasetRepository,
        permission_repository: PermissionRepository,
        permission_service: PermissionService,
        invitation_repository: DatasetInvitationRepository,
        anonymous_link_repository: DatasetAnonymousLinkRepository,
        user_repository: UserRepository,
        user_service: UserService,
        audit: DatasetAccessAudit,
        email_service: EmailService,
        public_base_url: str,
        tenancy_repository: TenancyRepository,
        membership_service: TenancyMembershipService,
        tenancy_invitations: TenancyInvitationService,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._datasets = dataset_service
        self._dataset_repository = dataset_repository
        self._permissions = permission_repository
        self._permission_service = permission_service
        self._invitations = invitation_repository
        self._anonymous_links = anonymous_link_repository
        self._users = user_repository
        self._user_service = user_service
        self._audit = audit
        self._email = email_service
        self._base_url = public_base_url.rstrip("/")
        self._clock = clock
        self._tenancies = tenancy_repository
        self._membership_service = membership_service
        self._tenancy_invitations = tenancy_invitations
        self._logger = logging.getLogger("service:ShareService")

    def invitation_link(self, token: str) -> str:
        return f"{self._base_url}/invitations/{token}"

    def _authorized(self, dataset_id: UUID, user_id: UUID):
        dataset, _, _ = self._datasets.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=None,
            action=DatasetAction.WRITE,
        )
        return dataset

    def _share_user(self, user_id: UUID | None) -> ShareUser | None:
        if user_id is None:
            return None
        user = self._users.fetch_by_id(id=user_id, is_enabled=True)
        if user is None:
            user = self._users.fetch_by_id(id=user_id, is_enabled=False)
        if user is None:
            return None
        return ShareUser(id=user.id, name=user.name, email=user.email)

    def _permission_view(self, permission) -> PermissionView:
        return PermissionView(
            user=self._share_user(permission.user_id),
            level=PermissionLevel(permission.level).value,
            granted_at=permission.created_at,
            granted_by=permission.granted_by,
        )

    def _invitation_view(self, invitation) -> InvitationView:
        return InvitationView(
            id=invitation.id,
            email=invitation.email,
            orcid=invitation.orcid,
            level=invitation.level,
            created_at=invitation.created_at,
            accepted_at=invitation.accepted_at,
            accepted_by=self._share_user(invitation.accepted_by),
            revoked_at=invitation.revoked_at,
        )

    def _address(self, invitation) -> str:
        return invitation.email if invitation.email else f"ORCID {invitation.orcid}"

    def _queue(self, **kwargs) -> None:
        try:
            self._email.enqueue(**kwargs)
        except Exception:
            self._logger.error(
                "email enqueue failed",
                exc_info=True,
                extra=fields(
                    template=kwargs.get("template"),
                    dataset_id=str(kwargs.get("related_id")),
                ),
            )

    def candidates(self, dataset_id: UUID, user_id: UUID, term: str) -> list[ShareUser]:
        dataset = self._authorized(dataset_id, user_id)
        if (
            len((term or "").strip()) < 2
            or not dataset.tenancy
            or is_default(dataset.tenancy)
        ):
            return []
        excluded = [dataset.owner_id] + [
            permission.user_id
            for permission in self._permissions.list_for_dataset(dataset.id)
        ]
        users = self._users.search_share_candidates(
            tenancy=dataset.tenancy,
            term=term.strip(),
            exclude_ids=[user for user in excluded if user is not None],
        )
        return [
            ShareUser(id=user.id, name=user.name, email=user.email) for user in users
        ]

    def preview(self, token: str) -> InvitationPreview:
        invitation = self._invitations.fetch_by_token_hash(hash_token(token))
        if invitation is None or invitation.revoked_at is not None:
            raise NotFoundException("invitation_not_found")
        dataset = self._dataset_repository.fetch(
            dataset_id=invitation.dataset_id, restrict_by_tenancy=False
        )
        if dataset is None:
            raise NotFoundException("invitation_not_found")
        inviter = self._share_user(invitation.invited_by)
        owner = self._share_user(dataset.owner_id)
        embargoed = (
            dataset.embargo_until is not None and dataset.embargo_until > self._clock()
        )
        accepted = invitation.accepted_at is not None
        return InvitationPreview(
            state="accepted" if accepted else "pending",
            dataset_name=dataset.name,
            inviter_name=inviter.name if inviter else "A DataMap user",
            owner_name=owner.name if owner else "the owner",
            level=invitation.level,
            invited_as=self._address(invitation),
            embargo_until=dataset.embargo_until if embargoed else None,
            accepted_at=invitation.accepted_at,
            dataset_id=dataset.id if accepted else None,
        )

    def state(self, dataset_id: UUID, user_id: UUID) -> ShareState:
        dataset, _, level = self._datasets.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=None,
            action=DatasetAction.WRITE,
        )
        invitations = self._invitations.list_for_dataset(dataset.id)
        invited_as = {
            invitation.accepted_by: self._address(invitation)
            for invitation in invitations
            if invitation.accepted_by is not None
        }
        permissions = []
        for permission in self._permissions.list_for_dataset(dataset.id):
            view = self._permission_view(permission)
            view.invited_as = invited_as.get(permission.user_id)
            permissions.append(view)
        embargoed = (
            dataset.embargo_until is not None and dataset.embargo_until > self._clock()
        )
        tenancy = None
        if dataset.tenancy and not embargoed:
            summary = self._membership_service.summary(dataset.tenancy)
            tenancy = TenancyAccess(
                name=summary.display_name,
                path=dataset.tenancy,
                members=self._users.count_in_tenancy(dataset.tenancy),
                members_can_edit=allows_member_edits(dataset),
                is_default=summary.is_default,
                is_legacy=summary.is_legacy,
                datasets=self._tenancies.count_datasets(dataset.tenancy),
            )
        tenancy_invitations, can_invite = self._tenancy_invitations.share_additions(
            dataset, level, user_id
        )
        return ShareState(
            owner=self._share_user(dataset.owner_id),
            permissions=permissions,
            invitations=[
                self._invitation_view(invitation) for invitation in invitations
            ],
            anonymous_links=[
                AnonymousLinkView(
                    id=link.id,
                    label=link.label,
                    created_at=link.created_at,
                    revoked_at=link.revoked_at,
                    views=AnonymousLinkViews(count=count, first_at=first, last_at=last),
                    token_hint=link.token_hint,
                )
                for link, count, first, last in self._anonymous_links.list_with_views(
                    dataset.id
                )
            ],
            tenancy=tenancy,
            tenancy_invitations=tenancy_invitations,
            can_invite_to_tenancy=can_invite,
        )

    def grant(
        self, dataset_id: UUID, user_id: UUID, request: GrantRequest
    ) -> GrantResult:
        targets = [
            value
            for value in (request.user_id, request.email, request.orcid)
            if value not in (None, "")
        ]
        if not targets:
            raise _bad("share_target_required")
        if len(targets) > 1:
            raise _bad("share_target_ambiguous")
        try:
            level = PermissionLevel(request.level)
        except ValueError:
            raise _bad("invalid_level")

        dataset = self._authorized(dataset_id, user_id)

        email = normalise_email(request.email) if request.email else None
        orcid = normalise_orcid(request.orcid) if request.orcid else None
        if request.user_id is not None:
            target = self._users.fetch_by_id(id=request.user_id, is_enabled=True)
            if target is None:
                raise _bad("unknown_user")
        else:
            target = find_account(self._users, email, orcid)

        if target is not None:
            return self._grant_to_account(dataset, user_id, target, level)
        return self._invite(dataset, user_id, email, orcid, level)

    def _grant_to_account(
        self, dataset, user_id: UUID, target, level: PermissionLevel
    ) -> GrantResult:
        if target.id == dataset.owner_id:
            raise _bad("cannot_share_with_owner")
        if self._permissions.fetch(dataset.id, target.id) is not None:
            raise _bad("already_has_access")

        permission = self._permission_service.grant(
            dataset.id, target.id, level, user_id
        )
        if target.email:
            granter = self._share_user(user_id)
            self._queue(
                template=EmailTemplate.NOTIFICATION.value,
                recipient=target.email,
                context=self._access_granted_context(
                    dataset, granter.name if granter else None, level
                ),
                related_type="dataset",
                related_id=dataset.id,
                triggered_by=user_id,
            )
        return GrantResult(
            kind="permission", permission=self._permission_view(permission)
        )

    def _access_granted_context(
        self, dataset, granter_name: str | None, level: PermissionLevel
    ) -> dict:
        access = "edit" if level is PermissionLevel.WRITE else "read"
        what = f"{access} access to the dataset “{dataset.name}” on DataMap"
        return {
            "title": f"You now have access to “{dataset.name}”",
            "preheader": f"You now have {what}.",
            "actor_name": granter_name or None,
            "message": f"gave you {what}."
            if granter_name
            else f"You were given {what}.",
            "details": [
                {"label": "Dataset", "value": dataset.name},
                {"label": "Access", "value": access.capitalize()},
            ],
            "cta_label": "Open dataset",
            "cta_url": f"{self._base_url}/app/datasets/{dataset.id}",
            "reason": "You received this email because someone gave you access to a dataset on DataMap.",
        }

    def _invite(
        self,
        dataset,
        user_id: UUID,
        email: str | None,
        orcid: str | None,
        level: PermissionLevel,
    ) -> GrantResult:
        if self._invitations.find_pending(dataset.id, email, orcid) is not None:
            raise _bad("already_has_access")

        token = new_token()
        invitation = self._invitations.create(
            DatasetInvitation(
                dataset_id=dataset.id,
                email=email,
                orcid=orcid,
                level=level.value,
                token_hash=hash_token(token),
                invited_by=user_id,
            )
        )
        link = self.invitation_link(token)
        self._audit.record(
            dataset_id=dataset.id,
            event_type=AccessEventType.INVITATION_CREATED,
            changed_by=user_id,
            new_value={"invitation_id": str(invitation.id), "level": level.value},
        )
        if email is not None:
            inviter = self._share_user(user_id)
            embargoed = (
                dataset.embargo_until is not None
                and dataset.embargo_until > self._clock()
            )
            self._queue(
                template=EmailTemplate.DATASET_INVITATION.value,
                recipient=email,
                context={
                    "dataset_name": dataset.name,
                    "inviter_name": inviter.name
                    if inviter and inviter.name
                    else "A DataMap user",
                    "inviter_email": inviter.email
                    if inviter and deliverable(inviter.email)
                    else None,
                    "invited_address": email,
                    "level": level.value,
                    "embargo_until_date": long_date(dataset.embargo_until)
                    if embargoed
                    else None,
                    "note": dataset.embargo_note if embargoed else None,
                    "link": link,
                },
                secret_fields=frozenset({"link"}),
                related_type="dataset",
                related_id=dataset.id,
                triggered_by=user_id,
            )
        return GrantResult(
            kind="invitation", invitation=self._invitation_view(invitation), link=link
        )

    def update_permission(
        self, dataset_id: UUID, user_id: UUID, target_user_id: UUID, level: str
    ) -> PermissionView:
        try:
            new_level = PermissionLevel(level)
        except ValueError:
            raise _bad("invalid_level")
        dataset = self._authorized(dataset_id, user_id)
        current = self._permissions.fetch(dataset.id, target_user_id)
        if current is None:
            raise NotFoundException(f"not_found: {target_user_id}")
        permission = self._permission_service.grant(
            dataset.id, target_user_id, new_level, user_id
        )
        return self._permission_view(permission)

    def revoke_permission(
        self, dataset_id: UUID, user_id: UUID, target_user_id: UUID
    ) -> None:
        dataset = self._authorized(dataset_id, user_id)
        if not self._permission_service.revoke(dataset.id, target_user_id, user_id):
            raise NotFoundException(f"not_found: {target_user_id}")

    def revoke_invitation(
        self, dataset_id: UUID, user_id: UUID, invitation_id: UUID
    ) -> None:
        dataset = self._authorized(dataset_id, user_id)
        invitation = self._invitations.fetch(dataset.id, invitation_id)
        if (
            invitation is None
            or invitation.revoked_at is not None
            or invitation.accepted_at is not None
        ):
            raise NotFoundException(f"not_found: {invitation_id}")
        self._invitations.revoke(invitation_id, self._clock())
        self._audit.record(
            dataset_id=dataset.id,
            event_type=AccessEventType.INVITATION_REVOKED,
            changed_by=user_id,
            old_value={"invitation_id": str(invitation_id)},
        )

    def regenerate_link(
        self, dataset_id: UUID, user_id: UUID, invitation_id: UUID
    ) -> str:
        dataset = self._authorized(dataset_id, user_id)
        invitation = self._invitations.fetch(dataset.id, invitation_id)
        if (
            invitation is None
            or invitation.accepted_at is not None
            or invitation.revoked_at is not None
        ):
            raise NotFoundException(f"not_found: {invitation_id}")
        token = new_token()
        if not self._invitations.replace_token(invitation_id, hash_token(token)):
            raise NotFoundException(f"not_found: {invitation_id}")
        return self.invitation_link(token)

    def accept(self, token: str, user_id: UUID) -> AcceptResult:
        invitation = self._invitations.fetch_by_token_hash(hash_token(token))
        if invitation is None or invitation.revoked_at is not None:
            raise NotFoundException("invitation_not_found")
        if invitation.accepted_at is not None:
            raise ConflictException("invitation_already_accepted")
        user = self._user_service.fetch_by_id(user_id)
        result = self._accept(invitation, user.id)
        if result is None:
            raise ConflictException("invitation_already_accepted")
        return result

    def claim(self, user_id: UUID) -> list[AcceptResult]:
        user = self._user_service.fetch_by_id(user_id)
        email = user.email.lower() if deliverable(user.email) else None
        orcid = next(
            (
                provider.reference
                for provider in (user.providers or [])
                if provider.name == "orcid"
            ),
            None,
        )
        accepted = []
        for invitation in self._invitations.list_pending_for(email, orcid):
            result = self._accept(invitation, user.id)
            if result is not None:
                accepted.append(result)
        return accepted

    def _accept(self, invitation, user_id: UUID) -> AcceptResult | None:
        if not self._invitations.mark_accepted(invitation.id, user_id, self._clock()):
            return None
        dataset = self._dataset_repository.fetch(
            dataset_id=invitation.dataset_id, restrict_by_tenancy=False
        )
        if dataset is None:
            raise NotFoundException(f"not_found: {invitation.dataset_id}")
        if dataset.owner_id == user_id:
            return AcceptResult(dataset_id=invitation.dataset_id, level="owner")

        current = self._permissions.fetch(invitation.dataset_id, user_id)
        if current is not None and (
            current.level == PermissionLevel.WRITE.value
            or current.level == invitation.level
        ):
            return AcceptResult(dataset_id=invitation.dataset_id, level=current.level)

        self._permission_service.grant(
            invitation.dataset_id,
            user_id,
            PermissionLevel(invitation.level),
            getattr(invitation, "invited_by", None),
        )
        return AcceptResult(dataset_id=invitation.dataset_id, level=invitation.level)
