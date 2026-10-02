from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class ShareUser:
    id: UUID
    name: str
    email: str | None = None


@dataclass
class PermissionView:
    user: ShareUser
    level: str
    granted_at: datetime
    granted_by: UUID | None = None


@dataclass
class InvitationView:
    id: UUID
    email: str | None
    orcid: str | None
    level: str
    created_at: datetime
    accepted_at: datetime | None = None
    accepted_by: ShareUser | None = None
    revoked_at: datetime | None = None


@dataclass
class AnonymousLinkViews:
    count: int = 0
    first_at: datetime | None = None
    last_at: datetime | None = None


@dataclass
class AnonymousLinkView:
    id: UUID
    label: str
    created_at: datetime
    revoked_at: datetime | None = None
    views: AnonymousLinkViews = field(default_factory=AnonymousLinkViews)


@dataclass
class ShareState:
    owner: ShareUser | None
    permissions: list[PermissionView] = field(default_factory=list)
    invitations: list[InvitationView] = field(default_factory=list)
    anonymous_links: list[AnonymousLinkView] = field(default_factory=list)


@dataclass
class GrantRequest:
    level: str
    user_id: UUID | None = None
    email: str | None = None
    orcid: str | None = None


@dataclass
class GrantResult:
    kind: str
    permission: PermissionView | None = None
    invitation: InvitationView | None = None
    link: str | None = None


@dataclass
class AcceptResult:
    dataset_id: UUID
    level: str


@dataclass
class AnonymousVersion:
    name: str
    created_at: datetime
    file_count: int
    total_size_bytes: int


@dataclass
class AnonymousPage:
    state: str  # active | ended | published
    dataset_id: UUID
    embargo_until: datetime | None = None
    embargo_ended_at: datetime | None = None
    name: str | None = None
    data: dict = field(default_factory=dict)
    versions: list[AnonymousVersion] = field(default_factory=list)
