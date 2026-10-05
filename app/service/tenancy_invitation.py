import logging
from uuid import UUID

from app.exception.bad_request import BadRequestException
from app.exception.conflict import ConflictException
from app.exception.forbidden import ForbiddenException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.logging_config import fields
from app.model.tenancy import (
    TenancyEventType,
    TenancyInvitationStatus,
    TenancySummary,
)
from app.model.tenancy_access import (
    InviteeLookupView,
    Page,
    TenancyInvitationView,
    UserBrief,
    UserRef,
    WorkspaceInvitationView,
    WorkspaceMemberView,
)
from app.model.user import is_admin
from app.repository.tenancy import TenancyRepository
from app.repository.tenancy_invitation import TenancyInvitationRepository
from app.repository.tenancy_membership import TenancyMembershipRepository
from app.repository.user import UserRepository
from app.service.share_identity import (
    find_account,
    normalise_email,
    normalise_orcid,
)
from app.service.tenancy_membership import TenancyMembershipService, require_page
from app.service.tenancy_notifier import TenancyNotifier, after_commit
from app.service.user import UserService
from app.service.user_refs import orcid_of, user_brief, user_ref

PENDING = TenancyInvitationStatus.PENDING


class TenancyInvitationService:
    def __init__(
        self,
        invitations: TenancyInvitationRepository,
        memberships: TenancyMembershipRepository,
        membership_service: TenancyMembershipService,
        tenancies: TenancyRepository,
        users: UserRepository,
        user_service: UserService,
        notifier: TenancyNotifier,
    ) -> None:
        self._invitations = invitations
        self._memberships = memberships
        self._membership_service = membership_service
        self._tenancies = tenancies
        self._users = users
        self._user_service = user_service
        self._notifier = notifier
        self._logger = logging.getLogger("service:TenancyInvitationService")

    def members(
        self, user_id: UUID, tenancy: str, limit: int, offset: int
    ) -> Page[WorkspaceMemberView]:
        self._require_workspace(user_id, tenancy)
        require_page(limit, offset)
        users, total = self._memberships.list_members(tenancy, limit, offset)
        return Page(
            items=[
                WorkspaceMemberView(id=user.id, name=user.name, orcid=orcid_of(user))
                for user in users
            ],
            total_count=total,
            limit=limit,
            offset=offset,
        )

    def pending_in(self, user_id: UUID, tenancy: str) -> list[WorkspaceInvitationView]:
        self._require_workspace(user_id, tenancy)
        return [
            self._workspace_view(invitation, user_id)
            for invitation in self._invitations.pending_for_tenancy(tenancy)
        ]

    def lookup(self, user_id: UUID, tenancy: str, value: str) -> InviteeLookupView:
        self._require_workspace(user_id, tenancy)
        text = (value or "").strip()
        by_email = "@" in text
        target = None
        try:
            target = self._resolve(text, by_email)
        finally:
            self._logger.info(
                "invitee lookup",
                extra=fields(
                    user_id=str(user_id),
                    tenancy=tenancy,
                    lookup_by="email" if by_email else "orcid",
                    matched=target is not None,
                ),
            )
        member = self._memberships.is_member(target.id, tenancy)
        pending = self._invitations.has_pending(tenancy, target.id)
        return InviteeLookupView(
            user=UserBrief(
                id=target.id,
                name=target.name,
                email=target.email if by_email else None,
            ),
            tenancy_member=member,
            invitation_pending=pending,
            can_invite=not member and not pending,
        )

    def invite(
        self, user_id: UUID, tenancy: str, invitee_id: UUID
    ) -> WorkspaceInvitationView:
        self._require_workspace(user_id, tenancy)
        invitee = self._users.fetch_by_id(id=invitee_id, is_enabled=True)
        if invitee is None:
            raise NotFoundException("no_account")
        if self._memberships.is_member(invitee.id, tenancy):
            raise ConflictException("already_member")
        if self._invitations.has_pending(tenancy, invitee.id):
            raise ConflictException("invitation_pending")
        invitation = self._invitations.create(tenancy, invitee.id, user_id)
        after_commit(
            lambda: self._tell_invited(invitee, user_id, invitation),
            "invitation",
            invitation_id=str(invitation.id),
        )
        return self._workspace_view(invitation, user_id)

    def _tell_invited(self, invitee, inviter_id: UUID, invitation) -> None:
        inviter = self._users.fetch_any_by_id(inviter_id)
        inviter_name = inviter.name if inviter else "A DataMap user"
        summary = self._membership_service.summary(invitation.tenancy)
        self._notifier.invitation(invitee, inviter_name, summary, invitation.id)
        self._notifier.invitation_notice(invitee, inviter_name, summary, invitation.id)

    def withdraw(self, user_id: UUID, tenancy: str, invitation_id: UUID) -> None:
        self._require_workspace(user_id, tenancy)
        invitation = self._invitations.fetch(invitation_id)
        if (
            invitation is None
            or invitation.tenancy != tenancy
            or TenancyInvitationStatus(invitation.status) != PENDING
        ):
            raise NotFoundException("invitation_not_found")
        if invitation.invited_by != user_id:
            raise ForbiddenException(
                f"forbidden: withdraw {invitation_id} by {user_id}"
            )
        self._close(invitation.id, TenancyInvitationStatus.WITHDRAWN, user_id)

    def withdraw_as_admin(self, invitation_id: UUID, admin_id: UUID) -> None:
        self._close(invitation_id, TenancyInvitationStatus.WITHDRAWN, admin_id)

    def pending_for_user(self, user_id: UUID) -> list[TenancyInvitationView]:
        return [
            TenancyInvitationView(
                id=invitation.id,
                tenancy=self._membership_service.summary(invitation.tenancy),
                invited_by=user_ref(self._users, invitation.invited_by),
                datasets=self._tenancies.count_datasets(invitation.tenancy),
                created_at=invitation.created_at,
            )
            for invitation in self._invitations.pending_for_user(user_id)
        ]

    def accept(self, user_id: UUID, invitation_id: UUID) -> TenancySummary:
        invitation = self._theirs(user_id, invitation_id)
        row = self._tenancies.fetch_any(invitation.tenancy)
        if row is None or not row.is_enabled:
            raise ConflictException("tenancy_disabled")
        if not self._invitations.accept(invitation.id, user_id):
            raise NotFoundException("invitation_not_found")
        return self._membership_service.summary(invitation.tenancy)

    def decline(self, user_id: UUID, invitation_id: UUID) -> None:
        invitation = self._theirs(user_id, invitation_id)
        self._close(invitation.id, TenancyInvitationStatus.DECLINED, user_id)

    def _require_workspace(self, user_id: UUID, tenancy: str) -> None:
        if not self._memberships.is_member(user_id, tenancy) and not is_admin(
            self._user_service.roles_of(user_id)
        ):
            raise NotFoundException("tenancy_not_found")
        self._membership_service.require_open_for_members(tenancy)

    def _theirs(self, user_id: UUID, invitation_id: UUID):
        invitation = self._invitations.fetch(invitation_id)
        if (
            invitation is None
            or invitation.user_id != user_id
            or TenancyInvitationStatus(invitation.status) != PENDING
        ):
            raise NotFoundException("invitation_not_found")
        return invitation

    def _close(
        self, invitation_id: UUID, status: TenancyInvitationStatus, actor_id: UUID
    ) -> None:
        event_type = {
            TenancyInvitationStatus.WITHDRAWN: TenancyEventType.INVITATION_WITHDRAWN,
            TenancyInvitationStatus.DECLINED: TenancyEventType.INVITATION_DECLINED,
        }[status]
        if not self._invitations.close(invitation_id, status, actor_id, event_type):
            raise NotFoundException("invitation_not_found")

    def _resolve(self, text: str, by_email: bool):
        try:
            email = normalise_email(text) if by_email else None
            orcid = None if by_email else normalise_orcid(text)
        except BadRequestException:
            raise IllegalStateException("invalid_request")
        user = find_account(self._users, email, orcid)
        if user is None:
            raise NotFoundException("no_account")
        return user

    def _workspace_view(self, invitation, user_id: UUID) -> WorkspaceInvitationView:
        invitee = user_brief(self._users, invitation.user_id)
        return WorkspaceInvitationView(
            id=invitation.id,
            user=UserRef(id=invitee.id, name=invitee.name),
            invited_by=user_ref(self._users, invitation.invited_by),
            created_at=invitation.created_at,
            can_withdraw=invitation.invited_by == user_id,
        )
