from uuid import UUID

from app.exception.bad_request import BadRequestException
from app.exception.conflict import ConflictException
from app.exception.forbidden import ForbiddenException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.model.dataset_access import AccessLevel, DatasetAction
from app.model.tenancy import (
    TenancyEventType,
    TenancyInvitationStatus,
    TenancySummary,
    closed_to_members,
)
from app.model.tenancy_access import (
    DatasetRef,
    DatasetTenancyInvitationView,
    ShareLookupView,
    TenancyInvitationView,
    UserBrief,
    UserRef,
)
from app.repository.tenancy import TenancyRepository
from app.repository.tenancy_invitation import TenancyInvitationRepository
from app.repository.tenancy_membership import TenancyMembershipRepository
from app.repository.user import UserRepository
from app.service.dataset import DatasetService
from app.service.share_identity import (
    find_account,
    normalise_email,
    normalise_orcid,
)
from app.service.tenancy_membership import TenancyMembershipService
from app.service.tenancy_notifier import TenancyNotifier

EDITORS = (AccessLevel.OWNER, AccessLevel.WRITE)
PENDING = TenancyInvitationStatus.PENDING


class TenancyInvitationService:
    def __init__(
        self,
        dataset_service: DatasetService,
        invitations: TenancyInvitationRepository,
        memberships: TenancyMembershipRepository,
        membership_service: TenancyMembershipService,
        tenancies: TenancyRepository,
        users: UserRepository,
        notifier: TenancyNotifier,
    ) -> None:
        self._datasets = dataset_service
        self._invitations = invitations
        self._memberships = memberships
        self._membership_service = membership_service
        self._tenancies = tenancies
        self._users = users
        self._notifier = notifier

    def lookup(self, dataset_id: UUID, user_id: UUID, value: str) -> ShareLookupView:
        dataset, level = self._authorized(dataset_id, user_id)
        target = self._resolve(value)
        tenancy = dataset.tenancy
        member = bool(tenancy) and self._memberships.is_member(target.id, tenancy)
        pending = bool(tenancy) and self._invitations.has_pending(tenancy, target.id)
        return ShareLookupView(
            user=UserBrief(id=target.id, name=target.name, email=target.email),
            tenancy_member=member,
            invitation_pending=pending,
            can_invite=not member
            and not pending
            and self.may_invite(dataset, level, user_id),
        )

    def may_invite(self, dataset, level: AccessLevel, user_id: UUID) -> bool:
        tenancy = dataset.tenancy
        if level not in EDITORS or not tenancy:
            return False
        row = self._tenancies.fetch_any(tenancy)
        return closed_to_members(
            tenancy, row.is_enabled if row else None
        ) is None and self._memberships.is_member(user_id, tenancy)

    def invite(
        self, dataset_id: UUID, user_id: UUID, invitee_id: UUID
    ) -> DatasetTenancyInvitationView:
        dataset, level = self._authorized(dataset_id, user_id)
        tenancy = dataset.tenancy
        if (
            level not in EDITORS
            or not tenancy
            or not self._memberships.is_member(user_id, tenancy)
        ):
            raise ForbiddenException(f"forbidden: invite to {tenancy} by {user_id}")
        self._membership_service.require_open_for_members(tenancy)
        invitee = self._users.fetch_by_id(id=invitee_id, is_enabled=True)
        if invitee is None:
            raise NotFoundException("no_account")
        if self._memberships.is_member(invitee.id, tenancy):
            raise ConflictException("already_member")
        if self._invitations.has_pending(tenancy, invitee.id):
            raise ConflictException("invitation_pending")
        invitation = self._invitations.create(tenancy, invitee.id, user_id, dataset.id)
        inviter = self._users.fetch_any_by_id(user_id)
        inviter_name = inviter.name if inviter else "A DataMap user"
        summary = self._membership_service.summary(tenancy)
        self._notifier.invitation(
            invitee, inviter_name, summary, dataset.name, invitation.id
        )
        self._notifier.invitation_notice(
            invitee, inviter_name, summary, dataset.name, invitation.id
        )
        return self._dataset_view(invitation, user_id)

    def withdraw(self, dataset_id: UUID, user_id: UUID, invitation_id: UUID) -> None:
        dataset, _ = self._authorized(dataset_id, user_id)
        invitation = self._invitations.fetch(invitation_id)
        if (
            invitation is None
            or invitation.dataset_id != dataset.id
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

    def share_additions(
        self, dataset, level: AccessLevel, user_id: UUID
    ) -> tuple[list[DatasetTenancyInvitationView], bool]:
        views = [
            self._dataset_view(invitation, user_id)
            for invitation in self._invitations.pending_for_dataset(dataset.id)
        ]
        return views, self.may_invite(dataset, level, user_id)

    def pending_for_user(self, user_id: UUID) -> list[TenancyInvitationView]:
        invitations = self._invitations.pending_for_user(user_id)
        names = self._invitations.dataset_names([i.dataset_id for i in invitations])
        return [
            TenancyInvitationView(
                id=invitation.id,
                tenancy=self._membership_service.summary(invitation.tenancy),
                invited_by=self._ref(invitation.invited_by),
                dataset=DatasetRef(
                    id=invitation.dataset_id, name=names[invitation.dataset_id]
                )
                if invitation.dataset_id in names
                else None,
                datasets=self._tenancies.count_datasets(invitation.tenancy),
                created_at=invitation.created_at,
            )
            for invitation in invitations
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

    def _authorized(self, dataset_id: UUID, user_id: UUID):
        dataset, _, level = self._datasets.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=None,
            action=DatasetAction.WRITE,
        )
        return dataset, level

    def _resolve(self, value: str):
        text = (value or "").strip()
        try:
            email = normalise_email(text) if "@" in text else None
            orcid = None if email else normalise_orcid(text)
        except BadRequestException:
            raise IllegalStateException("invalid_request")
        user = find_account(self._users, email, orcid)
        if user is None:
            raise NotFoundException("no_account")
        return user

    def _dataset_view(self, invitation, user_id: UUID) -> DatasetTenancyInvitationView:
        return DatasetTenancyInvitationView(
            id=invitation.id,
            user=self._brief(invitation.user_id),
            invited_by=self._brief(invitation.invited_by)
            if invitation.invited_by
            else None,
            created_at=invitation.created_at,
            can_withdraw=invitation.invited_by == user_id,
        )

    def _brief(self, user_id: UUID) -> UserBrief:
        user = self._users.fetch_any_by_id(user_id)
        if user is None:
            return UserBrief(id=user_id, name="Deleted account", email=None)
        return UserBrief(id=user.id, name=user.name, email=user.email)

    def _ref(self, user_id: UUID | None) -> UserRef | None:
        if user_id is None:
            return None
        user = self._users.fetch_any_by_id(user_id)
        return UserRef(id=user.id, name=user.name) if user else None
