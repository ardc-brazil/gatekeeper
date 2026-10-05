from dataclasses import dataclass, field
from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID

from app.model.tenancy import TenancySummary

T = TypeVar("T")


@dataclass
class UserRef:
    id: UUID
    name: str


@dataclass
class UserBrief:
    id: UUID
    name: str
    email: str | None = None


@dataclass
class DatasetRef:
    id: UUID
    name: str


@dataclass
class Page(Generic[T]):
    items: list[T]
    total_count: int
    limit: int
    offset: int


@dataclass
class NewTenancy:
    display_name: str
    namespace: str


@dataclass
class TenancyRequestView:
    id: UUID
    requested_name: str
    reason: str
    status: str
    tenancy: TenancySummary | None
    created_tenancy: bool
    decision_message: str | None
    created_at: datetime
    decided_at: datetime | None


@dataclass
class Requester:
    id: UUID
    name: str
    email: str | None
    email_verified: bool
    orcid: str | None


@dataclass
class AdminTenancyRequestView:
    id: UUID
    requester: Requester
    requested_name: str
    reason: str
    status: str
    kind: str
    suggested_tenancy: TenancySummary | None
    created_at: datetime
    tenancy: TenancySummary | None
    created_tenancy: bool
    decision_message: str | None
    decided_by: UserRef | None
    decided_at: datetime | None


@dataclass
class AdminTenancyRequestDetailView(AdminTenancyRequestView):
    requester_tenancies: list[TenancySummary] = field(default_factory=list)
    suggested_tenancy_members: int | None = None


@dataclass
class RequestCounts:
    open: int
    join: int
    new: int
    closed: int


@dataclass
class TenancyInvitationView:
    id: UUID
    tenancy: TenancySummary
    invited_by: UserRef | None
    dataset: DatasetRef | None
    datasets: int
    created_at: datetime


@dataclass
class DatasetTenancyInvitationView:
    id: UUID
    user: UserBrief
    invited_by: UserBrief | None
    created_at: datetime
    can_withdraw: bool


@dataclass
class ShareLookupView:
    user: UserBrief
    tenancy_member: bool
    invitation_pending: bool
    can_invite: bool


@dataclass
class AdminTenancyView:
    path: str
    display_name: str
    members: int
    datasets: int
    is_default: bool
    is_legacy: bool
    is_enabled: bool


@dataclass
class TenancyMemberView:
    id: UUID
    name: str
    email: str | None
    since: datetime
    invited_by: UserRef | None


@dataclass
class AdminTenancyInvitationView:
    id: UUID
    user: UserBrief
    invited_by: UserRef | None
    dataset: DatasetRef | None
    created_at: datetime


@dataclass
class TenancyMembersView:
    members: Page[TenancyMemberView]
    invitations: list[AdminTenancyInvitationView]


@dataclass
class RemovalImpactView:
    member_since: datetime
    datasets_in_tenancy: int
    shared_with_user: int
    owned_by_user: int
