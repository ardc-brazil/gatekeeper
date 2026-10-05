import enum
import re
from dataclasses import dataclass
from datetime import datetime

DEFAULT_TENANCY = "datamap/production/public"
PRODUCTION_PREFIX = "datamap/production/"
LEGACY_PREFIX = "datamap/staging/"
RESERVED_NAMESPACE = "public"
NAMESPACE_PATTERN = re.compile(r"^[a-z0-9-]+\Z")
NAMESPACE_MIN_LENGTH = 2
NAMESPACE_MAX_LENGTH = 63
DISPLAY_NAME_MAX_LENGTH = 64
TENANCY_NAME_MAX_LENGTH = 128
REASON_MAX_LENGTH = 1000
MESSAGE_MAX_LENGTH = 1000


@dataclass
class Tenancy:
    name: str
    is_enabled: bool = True
    created_at: datetime = None
    updated_at: datetime = None
    display_name: str | None = None


@dataclass
class TenancySummary:
    path: str
    display_name: str
    is_default: bool
    is_legacy: bool


class TenancyRequestStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"


class TenancyInvitationStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"
    REVOKED = "revoked"


class TenancyEventType(str, enum.Enum):
    TENANCY_CREATED = "tenancy_created"
    MEMBER_ADDED = "member_added"
    MEMBER_REMOVED = "member_removed"
    REQUEST_CREATED = "request_created"
    REQUEST_APPROVED = "request_approved"
    REQUEST_DECLINED = "request_declined"
    REQUEST_WITHDRAWN = "request_withdrawn"
    INVITATION_CREATED = "invitation_created"
    INVITATION_ACCEPTED = "invitation_accepted"
    INVITATION_DECLINED = "invitation_declined"
    INVITATION_WITHDRAWN = "invitation_withdrawn"


def is_default(path: str | None) -> bool:
    return path == DEFAULT_TENANCY


def is_legacy(path: str | None) -> bool:
    return bool(path) and path.startswith(LEGACY_PREFIX)


def is_production(path: str | None) -> bool:
    return bool(path) and path.startswith(PRODUCTION_PREFIX)


def namespace_of(path: str) -> str:
    return path.rstrip("/").rsplit("/", 1)[-1]


def derived_display_name(path: str) -> str:
    return namespace_of(path).replace("-", " ").replace("_", " ").title()


def display_name_of(path: str, display_name: str | None) -> str:
    return display_name or derived_display_name(path)


def summary_of(path: str, display_name: str | None) -> TenancySummary:
    return TenancySummary(
        path=path,
        display_name=display_name_of(path, display_name),
        is_default=is_default(path),
        is_legacy=is_legacy(path),
    )


def tenancy_order(path: str, display_name: str) -> tuple[int, str]:
    if is_default(path):
        return (0, "")
    if is_legacy(path):
        return (2, path)
    return (1, display_name.casefold())


def match_key(value: str) -> str:
    return re.sub(r"[\s-]+", "-", (value or "").strip().casefold()).strip("-")


def namespace_is_valid(namespace: str) -> bool:
    return (
        NAMESPACE_MIN_LENGTH <= len(namespace) <= NAMESPACE_MAX_LENGTH
        and NAMESPACE_PATTERN.match(namespace) is not None
        and namespace != RESERVED_NAMESPACE
    )


def trimmed_within(value: str | None, minimum: int, maximum: int) -> str | None:
    text = (value or "").strip()
    return text if minimum <= len(text) <= maximum else None
