from uuid import UUID

from app.exception.conflict import ConflictException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.model.db.tenancy import Tenancy as TenancyDBModel
from app.model.tenancy import (
    DISPLAY_NAME_MAX_LENGTH,
    PRODUCTION_PREFIX,
    TenancySummary,
    closed_to_members,
    display_name_of,
    is_production,
    namespace_is_valid,
    summary_of,
    tenancy_order,
    trimmed_within,
)
from app.repository.tenancy import TenancyRepository
from app.repository.tenancy_membership import TenancyMembershipRepository
from app.repository.user import UserRepository
from app.service.tenancy_notifier import TenancyNotifier

MAX_PAGE = 100


def require_page(limit: int, offset: int) -> None:
    if not 1 <= limit <= MAX_PAGE or offset < 0:
        raise IllegalStateException("invalid_request")


class TenancyMembershipService:
    def __init__(
        self,
        tenancies: TenancyRepository,
        memberships: TenancyMembershipRepository,
        users: UserRepository,
        notifier: TenancyNotifier,
    ) -> None:
        self._tenancies = tenancies
        self._memberships = memberships
        self._users = users
        self._notifier = notifier

    def summary(self, path: str) -> TenancySummary:
        row = self._tenancies.fetch_any(path)
        return summary_of(path, row.display_name if row else None)

    def summaries_for(self, user_id: UUID) -> list[TenancySummary]:
        summaries = [
            summary_of(row.name, row.display_name)
            for row in self._memberships.tenancies_of(user_id)
        ]
        return sorted(summaries, key=lambda s: tenancy_order(s.path, s.display_name))

    def require_open_for_members(self, path: str) -> TenancyDBModel:
        row = self._tenancies.fetch_any(path)
        code = closed_to_members(path, row.is_enabled if row else None)
        if row is None:
            raise NotFoundException(code)
        if code is not None:
            raise ConflictException(code)
        return row

    def check_new_tenancy(self, display_name: str, namespace: str) -> tuple[str, str]:
        slug = (namespace or "").strip()
        if not namespace_is_valid(slug):
            raise IllegalStateException("namespace_invalid")
        name = trimmed_within(display_name, 1, DISPLAY_NAME_MAX_LENGTH)
        if name is None:
            raise IllegalStateException("display_name_invalid")
        path = PRODUCTION_PREFIX + slug
        if self._tenancies.fetch_any(path) is not None:
            raise ConflictException("tenancy_exists")
        if self.display_name_taken(name):
            raise ConflictException("display_name_taken")
        return path, name

    def display_name_taken(self, name: str) -> bool:
        wanted = name.casefold()
        return any(
            display_name_of(row.name, row.display_name).casefold() == wanted
            for row in self._tenancies.list_all()
            if row.is_enabled and is_production(row.name)
        )

    def announce_access(
        self, user_id: UUID, admin_id: UUID, path: str, event_id: UUID
    ) -> None:
        user = self._users.fetch_any_by_id(user_id)
        if user is None:
            return
        admin = self._users.fetch_any_by_id(admin_id)
        self._notifier.access_granted(
            user,
            admin.name if admin else "An administrator",
            self.summary(path),
            self._tenancies.count_datasets(path),
            event_id,
        )
