from datetime import datetime, timedelta
from typing import Callable
from uuid import UUID

from app.exception.conflict import ConflictException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.exception.too_many_requests import TooManyRequestsException
from app.model.dataset_access import utcnow
from app.model.tenancy import (
    REASON_MAX_LENGTH,
    TENANCY_NAME_MAX_LENGTH,
    TenancyRequestStatus,
    trimmed_within,
)
from app.model.tenancy_access import TenancyRequestView
from app.repository.tenancy import TenancyRepository
from app.repository.tenancy_membership import TenancyMembershipRepository
from app.repository.tenancy_request import TenancyRequestRepository
from app.repository.user import UserRepository
from app.service.tenancy_membership import TenancyMembershipService
from app.service.tenancy_notifier import TenancyNotifier

DAILY_LIMIT = 3
WINDOW = timedelta(hours=24)
LATEST = 5


class TenancyRequestService:
    def __init__(
        self,
        requests: TenancyRequestRepository,
        tenancies: TenancyRepository,
        memberships: TenancyMembershipRepository,
        membership_service: TenancyMembershipService,
        users: UserRepository,
        notifier: TenancyNotifier,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._requests = requests
        self._tenancies = tenancies
        self._memberships = memberships
        self._membership_service = membership_service
        self._users = users
        self._notifier = notifier
        self._clock = clock

    def list_for_user(self, user_id: UUID) -> list[TenancyRequestView]:
        return [self._user_view(r) for r in self._requests.latest_for(user_id, LATEST)]

    def create(
        self, user_id: UUID, tenancy_name: str, reason: str
    ) -> TenancyRequestView:
        name = trimmed_within(tenancy_name, 1, TENANCY_NAME_MAX_LENGTH)
        if name is None:
            raise IllegalStateException("tenancy_name_invalid")
        why = trimmed_within(reason, 1, REASON_MAX_LENGTH)
        if why is None:
            raise IllegalStateException("reason_invalid")
        if self._requests.pending_for(user_id) is not None:
            raise ConflictException("request_pending")
        if self._requests.count_since(user_id, self._clock() - WINDOW) >= DAILY_LIMIT:
            raise TooManyRequestsException("too_many_requests")
        request = self._requests.create(user_id, name, why)
        requester = self._users.fetch_any_by_id(user_id)
        if requester is not None:
            self._notifier.request_received(request, requester)
        return self._user_view(request)

    def withdraw(self, user_id: UUID, request_id: UUID) -> None:
        if not self._requests.withdraw(request_id, user_id):
            raise NotFoundException("request_not_found")

    def _user_view(self, request) -> TenancyRequestView:
        return TenancyRequestView(
            id=request.id,
            requested_name=request.requested_name,
            reason=request.reason,
            status=TenancyRequestStatus(request.status).value,
            tenancy=self._membership_service.summary(request.tenancy)
            if request.tenancy
            else None,
            created_tenancy=bool(request.created_tenancy),
            decision_message=request.decision_message,
            created_at=request.created_at,
            decided_at=request.decided_at,
        )
