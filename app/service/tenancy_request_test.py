import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.exception.conflict import ConflictException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.exception.too_many_requests import TooManyRequestsException
from app.model.tenancy import TenancyRequestStatus, summary_of
from app.repository.tenancy import TenancyRepository
from app.repository.tenancy_membership import TenancyMembershipRepository
from app.repository.tenancy_request import TenancyRequestRepository
from app.repository.user import UserRepository
from app.service.tenancy_membership import TenancyMembershipService
from app.service.tenancy_notifier import TenancyNotifier
from app.service.tenancy_request import TenancyRequestService

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
ATTO = "datamap/production/atto"


def request_row(user_id, **overrides):
    values = dict(
        id=uuid4(),
        user_id=user_id,
        requested_name="ATTO",
        reason="Fluxes",
        status=TenancyRequestStatus.PENDING,
        tenancy=None,
        created_tenancy=False,
        decision_message=None,
        decided_by=None,
        decided_at=None,
        created_at=NOW,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def tenancy_row(name, display_name=None, is_enabled=True):
    return SimpleNamespace(name=name, display_name=display_name, is_enabled=is_enabled)


def user_row(name="Bruna Costa", email="bruna@usp.br", verified=True, orcid=None):
    providers = [SimpleNamespace(name="orcid", reference=orcid)] if orcid else []
    return SimpleNamespace(
        id=uuid4(),
        name=name,
        email=email,
        email_verified_at=NOW if verified else None,
        providers=providers,
        created_at=NOW,
    )


class RequestServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.requests = Mock(spec=TenancyRequestRepository)
        self.tenancies = Mock(spec=TenancyRepository)
        self.memberships = Mock(spec=TenancyMembershipRepository)
        self.membership_service = Mock(spec=TenancyMembershipService)
        self.membership_service.summary.side_effect = lambda path: summary_of(
            path, "ATTO" if path == ATTO else None
        )
        self.users = Mock(spec=UserRepository)
        self.notifier = Mock(spec=TenancyNotifier)
        self.user = user_row()
        self.users.fetch_any_by_id.side_effect = lambda id: (
            self.user if id == self.user.id else None
        )
        self.requests.pending_for.return_value = None
        self.requests.count_since.return_value = 0
        self.requests.create.side_effect = (
            lambda user_id, requested_name, reason: request_row(
                user_id, requested_name=requested_name, reason=reason
            )
        )
        self.service = TenancyRequestService(
            requests=self.requests,
            tenancies=self.tenancies,
            memberships=self.memberships,
            membership_service=self.membership_service,
            users=self.users,
            notifier=self.notifier,
            clock=lambda: NOW,
        )


class TestCreate(RequestServiceTestCase):
    def code(self, name, reason) -> str:
        with self.assertRaises(
            (IllegalStateException, ConflictException, TooManyRequestsException)
        ) as raised:
            self.service.create(self.user.id, name, reason)
        return str(raised.exception)

    def test_a_request_is_stored_trimmed_and_the_admins_are_told(self):
        view = self.service.create(self.user.id, "  ATTO ", " Fluxes ")

        self.requests.create.assert_called_once_with(self.user.id, "ATTO", "Fluxes")
        self.assertEqual(view.status, "pending")
        self.assertEqual(view.requested_name, "ATTO")
        self.assertIsNone(view.tenancy)
        (request, requester), _ = self.notifier.request_received.call_args
        self.assertEqual(request.requested_name, "ATTO")
        self.assertIs(requester, self.user)

    def test_the_lengths(self):
        self.assertEqual(self.code("   ", "why"), "tenancy_name_invalid")
        self.assertEqual(self.code("x" * 129, "why"), "tenancy_name_invalid")
        self.assertEqual(self.code("ATTO", ""), "reason_invalid")
        self.assertEqual(self.code("ATTO", "x" * 1001), "reason_invalid")
        self.requests.create.assert_not_called()

    def test_one_pending_request_per_user(self):
        self.requests.pending_for.return_value = request_row(self.user.id)

        self.assertEqual(self.code("ATTO", "why"), "request_pending")

    def test_three_a_day_withdrawn_included(self):
        self.requests.count_since.return_value = 3

        self.assertEqual(self.code("ATTO", "why"), "too_many_requests")
        self.requests.count_since.assert_called_once_with(
            self.user.id, NOW - timedelta(hours=24)
        )

    def test_two_today_still_allows_a_third(self):
        self.requests.count_since.return_value = 2

        self.assertEqual(
            self.service.create(self.user.id, "ATTO", "why").status, "pending"
        )


class TestUserSide(RequestServiceTestCase):
    def test_the_latest_five_with_the_tenancy_once_approved(self):
        approved = request_row(
            self.user.id,
            status=TenancyRequestStatus.APPROVED,
            tenancy=ATTO,
            decided_at=NOW,
        )
        declined = request_row(
            self.user.id,
            status=TenancyRequestStatus.DECLINED,
            decision_message="Ask Alan",
        )
        self.requests.latest_for.return_value = [approved, declined]

        views = self.service.list_for_user(self.user.id)

        self.requests.latest_for.assert_called_once_with(self.user.id, 5)
        self.assertEqual(views[0].tenancy, summary_of(ATTO, "ATTO"))
        self.assertEqual(views[0].status, "approved")
        self.assertIsNone(views[1].tenancy)
        self.assertEqual(views[1].decision_message, "Ask Alan")

    def test_withdrawing_what_is_not_pending_or_not_theirs_is_not_found(self):
        self.requests.withdraw.return_value = False

        with self.assertRaises(NotFoundException) as raised:
            self.service.withdraw(self.user.id, uuid4())

        self.assertEqual(str(raised.exception), "request_not_found")

    def test_a_withdrawal_is_passed_to_the_repository_as_the_user(self):
        self.requests.withdraw.return_value = True
        request_id = uuid4()

        self.service.withdraw(self.user.id, request_id)

        self.requests.withdraw.assert_called_once_with(request_id, self.user.id)
