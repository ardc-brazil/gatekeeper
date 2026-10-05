from datetime import datetime
from typing import List
from uuid import UUID

from app.exception.conflict import ConflictException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.model.tenancy import (
    display_name_of,
    is_default,
    is_legacy,
    tenancy_order,
)
from app.model.tenancy_access import (
    AdminTenancyInvitationView,
    AdminTenancyView,
    Page,
    RemovalImpactView,
    TenancyMembersView,
    TenancyMemberView,
    UserBrief,
)
from app.repository.tenancy import TenancyRepository
from app.repository.tenancy_invitation import TenancyInvitationRepository
from app.repository.tenancy_membership import TenancyMembershipRepository
from app.repository.user import UserRepository
from app.service.tenancy_membership import TenancyMembershipService
from app.service.user_refs import dataset_ref, user_brief, user_ref

MAX_PAGE = 100
SEARCH_LIMIT = 10
SEARCH_MIN_LENGTH = 2


class TenancyAdminService:
    def __init__(
        self,
        tenancies: TenancyRepository,
        memberships: TenancyMembershipRepository,
        membership_service: TenancyMembershipService,
        invitations: TenancyInvitationRepository,
        users: UserRepository,
    ) -> None:
        self._tenancies = tenancies
        self._memberships = memberships
        self._membership_service = membership_service
        self._invitations = invitations
        self._users = users

    def list(self) -> List[AdminTenancyView]:
        members = self._tenancies.member_counts()
        datasets = self._tenancies.dataset_counts()
        views = [
            AdminTenancyView(
                path=row.name,
                display_name=display_name_of(row.name, row.display_name),
                members=members.get(row.name, 0),
                datasets=datasets.get(row.name, 0),
                is_default=is_default(row.name),
                is_legacy=is_legacy(row.name),
                is_enabled=row.is_enabled,
            )
            for row in self._tenancies.list_all()
        ]
        return sorted(views, key=lambda v: tenancy_order(v.path, v.display_name))

    def create(
        self, admin_id: UUID, display_name: str, namespace: str
    ) -> AdminTenancyView:
        path, name = self._membership_service.check_new_tenancy(display_name, namespace)
        self._tenancies.create_with_event(path, name, admin_id)
        return AdminTenancyView(
            path=path,
            display_name=name,
            members=0,
            datasets=0,
            is_default=False,
            is_legacy=False,
            is_enabled=True,
        )

    def members(self, path: str, limit: int, offset: int) -> TenancyMembersView:
        self._existing(path)
        if not 1 <= limit <= MAX_PAGE or offset < 0:
            raise IllegalStateException("invalid_request")
        users, total = self._memberships.list_members(path, limit, offset)
        ids = [user.id for user in users]
        since = self._memberships.added_at(path, ids)
        inviters = self._memberships.inviters(path, ids)
        items = [
            TenancyMemberView(
                id=user.id,
                name=user.name,
                email=user.email,
                since=since.get(user.id, user.created_at),
                invited_by=user_ref(self._users, inviters.get(user.id)),
            )
            for user in users
        ]
        return TenancyMembersView(
            members=Page(items=items, total_count=total, limit=limit, offset=offset),
            invitations=[]
            if is_default(path) or is_legacy(path)
            else self._pending_invitations(path),
        )

    def removal_impact(self, path: str, user_id: UUID) -> RemovalImpactView:
        self._existing(path)
        user = self._users.fetch_any_by_id(user_id)
        if user is None or not self._memberships.is_member(user_id, path):
            raise NotFoundException("member_not_found")
        in_tenancy, shared, owned = self._memberships.removal_counts(path, user_id)
        return RemovalImpactView(
            member_since=self._member_since(path, user),
            datasets_in_tenancy=in_tenancy,
            shared_with_user=shared,
            owned_by_user=owned,
        )

    def add(self, path: str, user_id: UUID, admin_id: UUID) -> TenancyMemberView:
        self._membership_service.require_open_for_members(path)
        user = self._users.fetch_by_id(id=user_id, is_enabled=True)
        if user is None:
            raise NotFoundException("no_account")
        if self._memberships.is_member(user_id, path):
            raise ConflictException("already_member")
        event_id = self._memberships.add(path, user_id, admin_id)
        if event_id is None:
            raise ConflictException("already_member")
        self._membership_service.announce_access(user_id, admin_id, path, event_id)
        return TenancyMemberView(
            id=user.id,
            name=user.name,
            email=user.email,
            since=self._member_since(path, user),
            invited_by=None,
        )

    def _member_since(self, path: str, user) -> datetime:
        return self._memberships.added_at(path, [user.id]).get(user.id, user.created_at)

    def remove(self, path: str, user_id: UUID, admin_id: UUID) -> None:
        self._existing(path)
        if is_default(path):
            raise ConflictException("public_tenancy_locked")
        if is_legacy(path):
            raise ConflictException("legacy_tenancy_read_only")
        if not self._memberships.remove(path, user_id, admin_id):
            raise NotFoundException("member_not_found")

    def search_users(self, q: str | None) -> List[UserBrief]:
        term = (q or "").strip()
        if len(term) < SEARCH_MIN_LENGTH:
            raise IllegalStateException("invalid_request")
        return [
            UserBrief(id=user.id, name=user.name, email=user.email)
            for user in self._users.search_admin(term, SEARCH_LIMIT)
        ]

    def _existing(self, path: str) -> None:
        if self._tenancies.fetch_any(path) is None:
            raise NotFoundException("tenancy_not_found")

    def _pending_invitations(self, path: str) -> List[AdminTenancyInvitationView]:
        invitations = self._invitations.pending_for_tenancy(path)
        names = self._invitations.dataset_names([i.dataset_id for i in invitations])
        return [
            AdminTenancyInvitationView(
                id=invitation.id,
                user=user_brief(self._users, invitation.user_id),
                invited_by=user_ref(self._users, invitation.invited_by),
                dataset=dataset_ref(names, invitation.dataset_id),
                created_at=invitation.created_at,
            )
            for invitation in invitations
        ]
