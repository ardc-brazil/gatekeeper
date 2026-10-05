from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class _FromViews(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TenancySummaryResponse(_FromViews):
    path: str
    display_name: str
    is_default: bool
    is_legacy: bool


class UserRefResponse(_FromViews):
    id: UUID
    name: str


class UserBriefResponse(_FromViews):
    id: UUID
    name: str
    email: str | None = None


class DatasetRefResponse(_FromViews):
    id: UUID
    name: str


class TenancyRequestResponse(_FromViews):
    id: UUID
    requested_name: str
    reason: str
    status: str
    tenancy: TenancySummaryResponse | None
    created_tenancy: bool
    decision_message: str | None
    created_at: datetime
    decided_at: datetime | None


class TenancyInvitationResponse(_FromViews):
    id: UUID
    tenancy: TenancySummaryResponse
    invited_by: UserRefResponse | None
    dataset: DatasetRefResponse | None
    datasets: int
    created_at: datetime


class AcceptedInvitationResponse(_FromViews):
    tenancy: TenancySummaryResponse


class DatasetTenancyInvitationResponse(_FromViews):
    id: UUID
    user: UserBriefResponse
    invited_by: UserBriefResponse | None
    created_at: datetime
    can_withdraw: bool


class ShareLookupResponse(_FromViews):
    user: UserBriefResponse
    tenancy_member: bool
    invitation_pending: bool
    can_invite: bool


class RequesterResponse(_FromViews):
    id: UUID
    name: str
    email: str | None
    email_verified: bool
    orcid: str | None


class AdminTenancyRequestResponse(_FromViews):
    id: UUID
    requester: RequesterResponse
    requested_name: str
    reason: str
    status: str
    kind: str
    suggested_tenancy: TenancySummaryResponse | None
    created_at: datetime
    tenancy: TenancySummaryResponse | None
    created_tenancy: bool
    decision_message: str | None
    decided_by: UserRefResponse | None
    decided_at: datetime | None


class AdminTenancyRequestDetailResponse(AdminTenancyRequestResponse):
    requester_tenancies: list[TenancySummaryResponse]
    suggested_tenancy_members: int | None


class AdminTenancyRequestPage(_FromViews):
    items: list[AdminTenancyRequestResponse]
    total_count: int
    limit: int
    offset: int


class RequestCountsResponse(_FromViews):
    open: int
    join: int
    new: int
    closed: int


class AdminTenancyResponse(_FromViews):
    path: str
    display_name: str
    members: int
    datasets: int
    is_default: bool
    is_legacy: bool
    is_enabled: bool


class TenancyMemberResponse(_FromViews):
    id: UUID
    name: str
    email: str | None
    since: datetime
    invited_by: UserRefResponse | None


class TenancyMemberPage(_FromViews):
    items: list[TenancyMemberResponse]
    total_count: int
    limit: int
    offset: int


class AdminTenancyInvitationResponse(_FromViews):
    id: UUID
    user: UserBriefResponse
    invited_by: UserRefResponse | None
    dataset: DatasetRefResponse | None
    created_at: datetime


class TenancyMembersResponse(_FromViews):
    members: TenancyMemberPage
    invitations: list[AdminTenancyInvitationResponse]


class RemovalImpactResponse(_FromViews):
    member_since: datetime
    datasets_in_tenancy: int
    shared_with_user: int
    owned_by_user: int


class TenancyRequestBody(BaseModel):
    tenancy_name: str
    reason: str


class NewTenancyBody(BaseModel):
    display_name: str
    namespace: str


class ApproveBody(BaseModel):
    tenancy: str | None = None
    new_tenancy: NewTenancyBody | None = None


class DeclineBody(BaseModel):
    message: str | None = None


class TenancyCreateBody(BaseModel):
    display_name: str
    namespace: str


class UserIdBody(BaseModel):
    user_id: UUID
