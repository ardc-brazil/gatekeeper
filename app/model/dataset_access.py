import enum
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

SHARED_ROLE = "datasets_shared"


class PermissionLevel(str, enum.Enum):
    READ = "read"
    WRITE = "write"


class AccessLevel(str, enum.Enum):
    OWNER = "owner"
    WRITE = "write"
    READ = "read"
    TENANCY = "tenancy"


class DatasetAction(enum.Enum):
    READ_METADATA = "read_metadata"
    READ_FILES = "read_files"
    WRITE = "write"
    DELETE = "delete"
    EXTEND_EMBARGO = "extend_embargo"
    MANAGE_EMBARGO = "manage_embargo"
    MANAGE_MEMBERS_ACCESS = "manage_members_access"


class AccessEventType(str, enum.Enum):
    CREATED = "created"
    EXTENDED = "extended"
    ENDED_EARLY = "ended_early"
    EXPIRED = "expired"
    METADATA_MODE_CHANGED = "metadata_mode_changed"
    NOTE_CHANGED = "note_changed"
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_REVOKED = "permission_revoked"
    INVITATION_CREATED = "invitation_created"
    INVITATION_REVOKED = "invitation_revoked"
    ANONYMOUS_LINK_CREATED = "anonymous_link_created"
    ANONYMOUS_LINK_REVOKED = "anonymous_link_revoked"
    MEMBERS_ACCESS_CHANGED = "members_access_changed"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class DatasetAccess:
    level: AccessLevel
    can_edit: bool
    can_share: bool
    can_manage_embargo: bool
    can_extend_embargo: bool
    can_delete: bool


@dataclass
class DatasetPermission:
    dataset_id: UUID
    user_id: UUID
    level: PermissionLevel
    granted_by: UUID | None = None
    created_at: datetime | None = None


@dataclass
class MembersAccess:
    members_can_edit: bool
    access: DatasetAccess
