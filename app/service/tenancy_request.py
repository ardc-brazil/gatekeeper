import dataclasses
from datetime import datetime, timedelta
from typing import Callable
from uuid import UUID

from app.exception.conflict import ConflictException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.exception.too_many_requests import TooManyRequestsException
from app.model.dataset_access import utcnow
from app.model.tenancy import (
    MESSAGE_MAX_LENGTH,
    REASON_MAX_LENGTH,
    TENANCY_NAME_MAX_LENGTH,
    TenancyRequestStatus,
    TenancySummary,
    is_default,
    is_production,
    match_key,
    namespace_of,
    summary_of,
    trimmed_within,
)
from app.model.tenancy_access import (
    AdminTenancyRequestDetailView,
    AdminTenancyRequestView,
    NewTenancy,
    Page,
    RequestCounts,
    Requester,
    TenancyRequestView,
    UserRef,
)
from app.repository.tenancy import TenancyRepository
from app.repository.tenancy_membership import TenancyMembershipRepository
from app.repository.tenancy_request import TenancyRequestRepository
from app.repository.user import UserRepository
from app.service.tenancy_membership import TenancyMembershipService
from app.service.tenancy_notifier import TenancyNotifier

DAILY_LIMIT = 3
WINDOW = timedelta(hours=24)
LATEST = 5
MAX_PAGE = 100


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

    def counts(self) -> RequestCounts:
        index = self._suggestion_index()
        pending = self._requests.list_pending(None)
        join = sum(1 for r in pending if match_key(r.requested_name) in index)
        return RequestCounts(
            open=len(pending),
            join=join,
            new=len(pending) - join,
            closed=self._requests.count_closed(),
        )

    def queue(
        self, status: str, kind: str | None, q: str | None, limit: int, offset: int
    ) -> Page[AdminTenancyRequestView]:
        if (
            status not in ("open", "closed")
            or kind not in (None, "join", "new")
            or not 1 <= limit <= MAX_PAGE
            or offset < 0
        ):
            raise IllegalStateException("invalid_request")
        term = (q or "").strip() or None
        index = self._suggestion_index()
        if status == "closed":
            rows, total = self._requests.list_closed(term, limit, offset)
            return Page(
                items=[self._admin_view(r, index) for r in rows],
                total_count=total,
                limit=limit,
                offset=offset,
            )
        views = [self._admin_view(r, index) for r in self._requests.list_pending(term)]
        if kind is not None:
            views = [v for v in views if v.kind == kind]
        return Page(
            items=views[offset : offset + limit],
            total_count=len(views),
            limit=limit,
            offset=offset,
        )

    def detail(self, request_id: UUID) -> AdminTenancyRequestDetailView:
        request = self._visible(request_id)
        view = self._admin_view(request, self._suggestion_index())
        suggested = view.suggested_tenancy
        return AdminTenancyRequestDetailView(
            **{
                f.name: getattr(view, f.name)
                for f in dataclasses.fields(AdminTenancyRequestView)
            },
            requester_tenancies=self._membership_service.summaries_for(request.user_id),
            suggested_tenancy_members=self._memberships.count(suggested.path)
            if suggested
            else None,
        )

    def approve(
        self,
        request_id: UUID,
        admin_id: UUID,
        tenancy: str | None,
        new_tenancy: NewTenancy | None,
    ) -> AdminTenancyRequestView:
        if (tenancy is None) == (new_tenancy is None):
            raise IllegalStateException("invalid_request")
        request = self._pending(request_id)
        if tenancy is not None:
            path, display_name = tenancy.strip(), None
            self._membership_service.require_open_for_members(path)
            if self._memberships.is_member(request.user_id, path):
                raise ConflictException("already_member")
        else:
            path, display_name = self._membership_service.check_new_tenancy(
                new_tenancy.display_name, new_tenancy.namespace
            )
            requester = self._users.fetch_any_by_id(request.user_id)
            if requester is None or requester.email_verified_at is None:
                raise ConflictException("requester_email_unverified")
        approved, event_id = self._requests.approve(
            request_id, admin_id, path, display_name, self._clock()
        )
        self._membership_service.announce_access(
            approved.user_id, admin_id, path, event_id
        )
        return self._admin_view(approved, self._suggestion_index())

    def decline(
        self, request_id: UUID, admin_id: UUID, message: str | None
    ) -> AdminTenancyRequestView:
        text = trimmed_within(message, 0, MESSAGE_MAX_LENGTH)
        if text is None:
            raise IllegalStateException("message_invalid")
        self._pending(request_id)
        declined = self._requests.decline(
            request_id, admin_id, text or None, self._clock()
        )
        user = self._users.fetch_any_by_id(declined.user_id)
        if user is not None:
            self._notifier.request_declined(user, declined)
        return self._admin_view(declined, self._suggestion_index())

    def _visible(self, request_id: UUID):
        request = self._requests.fetch(request_id)
        if (
            request is None
            or TenancyRequestStatus(request.status) == TenancyRequestStatus.WITHDRAWN
        ):
            raise NotFoundException("request_not_found")
        return request

    def _pending(self, request_id: UUID):
        request = self._visible(request_id)
        if TenancyRequestStatus(request.status) != TenancyRequestStatus.PENDING:
            raise ConflictException("request_not_pending")
        return request

    def _suggestion_index(self) -> dict[str, TenancySummary]:
        index: dict[str, TenancySummary] = {}
        for row in sorted(self._tenancies.list_all(), key=lambda r: r.name):
            if (
                not row.is_enabled
                or not is_production(row.name)
                or is_default(row.name)
            ):
                continue
            summary = summary_of(row.name, row.display_name)
            index.setdefault(match_key(summary.display_name), summary)
            index.setdefault(match_key(namespace_of(row.name)), summary)
        return index

    def _admin_view(
        self, request, index: dict[str, TenancySummary]
    ) -> AdminTenancyRequestView:
        suggestion = index.get(match_key(request.requested_name))
        return AdminTenancyRequestView(
            id=request.id,
            requester=self._requester(request.user_id),
            requested_name=request.requested_name,
            reason=request.reason,
            status=TenancyRequestStatus(request.status).value,
            kind="join" if suggestion else "new",
            suggested_tenancy=suggestion,
            created_at=request.created_at,
            tenancy=self._membership_service.summary(request.tenancy)
            if request.tenancy
            else None,
            created_tenancy=bool(request.created_tenancy),
            decision_message=request.decision_message,
            decided_by=self._user_ref(request.decided_by),
            decided_at=request.decided_at,
        )

    def _requester(self, user_id: UUID) -> Requester:
        user = self._users.fetch_any_by_id(user_id)
        if user is None:
            return Requester(
                id=user_id,
                name="Deleted account",
                email=None,
                email_verified=False,
                orcid=None,
            )
        orcid = next((p.reference for p in user.providers if p.name == "orcid"), None)
        return Requester(
            id=user.id,
            name=user.name,
            email=user.email,
            email_verified=user.email_verified_at is not None,
            orcid=orcid,
        )

    def _user_ref(self, user_id: UUID | None) -> UserRef | None:
        if user_id is None:
            return None
        user = self._users.fetch_any_by_id(user_id)
        return UserRef(id=user.id, name=user.name) if user else None

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
