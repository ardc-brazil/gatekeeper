import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.exception.conflict import ConflictException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.exception.too_many_requests import TooManyRequestsException
from app.model.tenancy import DEFAULT_TENANCY, TenancyRequestStatus, summary_of
from app.repository.tenancy import TenancyRepository
from app.repository.tenancy_membership import TenancyMembershipRepository
from app.repository.tenancy_request import TenancyRequestRepository
from app.model.tenancy_access import NewTenancy
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


class AdminQueueTestCase(RequestServiceTestCase):
    def setUp(self):
        super().setUp()
        self.admin = user_row(name="Luciana Rizzo")
        self.requester = user_row(orcid="0000-0002-1825-0097")
        people = {
            self.user.id: self.user,
            self.admin.id: self.admin,
            self.requester.id: self.requester,
        }
        self.users.fetch_any_by_id.side_effect = people.get
        self.tenancies.list_all.return_value = [
            tenancy_row(ATTO, "ATTO"),
            tenancy_row(DEFAULT_TENANCY, "Public"),
            tenancy_row("datamap/production/cerrado-flux"),
            tenancy_row("datamap/production/off", "Off", is_enabled=False),
            tenancy_row("datamap/staging/lba", "LBA"),
        ]

    def pending(self, name: str):
        return request_row(self.requester.id, requested_name=name)


class TestSuggestionsAndCounts(AdminQueueTestCase):
    def test_join_when_a_tenancy_matches_new_otherwise(self):
        self.requests.list_pending.return_value = [
            self.pending("atto"),
            self.pending("Cerrado Flux"),
            self.pending("Public"),
            self.pending("Off"),
            self.pending("LBA"),
            self.pending("Brand new"),
        ]
        self.requests.count_closed.return_value = 7

        counts = self.service.counts()

        self.assertEqual(
            (counts.open, counts.join, counts.new, counts.closed), (6, 2, 4, 7)
        )

    def test_a_row_carries_the_requester_and_the_suggestion(self):
        self.requests.list_pending.return_value = [self.pending("cerrado-flux")]

        page = self.service.queue("open", None, None, 50, 0)

        (row,) = page.items
        self.assertEqual(row.kind, "join")
        self.assertEqual(row.suggested_tenancy.path, "datamap/production/cerrado-flux")
        self.assertEqual(row.suggested_tenancy.display_name, "Cerrado Flux")
        self.assertEqual(row.requester.orcid, "0000-0002-1825-0097")
        self.assertTrue(row.requester.email_verified)
        self.assertIsNone(row.decided_by)


class TestQueue(AdminQueueTestCase):
    def test_open_is_filtered_by_kind_and_paged_after_filtering(self):
        self.requests.list_pending.return_value = [
            self.pending("ATTO"),
            self.pending("New one"),
            self.pending("Another new"),
        ]

        page = self.service.queue("open", "new", "  ana ", 1, 1)

        self.requests.list_pending.assert_called_once_with("ana")
        self.assertEqual(page.total_count, 2)
        self.assertEqual([r.requested_name for r in page.items], ["Another new"])
        self.assertEqual((page.limit, page.offset), (1, 1))

    def test_closed_is_paged_by_the_repository_and_ignores_kind(self):
        decided = request_row(
            self.requester.id,
            status=TenancyRequestStatus.DECLINED,
            decided_by=self.admin.id,
            decided_at=NOW,
        )
        self.requests.list_closed.return_value = ([decided], 9)

        page = self.service.queue("closed", "join", "", 5, 0)

        self.requests.list_closed.assert_called_once_with(None, 5, 0)
        self.assertEqual(page.total_count, 9)
        self.assertEqual(page.items[0].decided_by.name, "Luciana Rizzo")

    def test_parameters_out_of_range_are_invalid_request(self):
        for args in (
            ("pending", None, None, 50, 0),
            ("open", "both", None, 50, 0),
            ("open", None, None, 0, 0),
            ("open", None, None, 101, 0),
            ("open", None, None, 50, -1),
        ):
            with self.subTest(args=args):
                with self.assertRaises(IllegalStateException) as raised:
                    self.service.queue(*args)
                self.assertEqual(str(raised.exception), "invalid_request")


class TestDetail(AdminQueueTestCase):
    def test_the_requesters_tenancies_and_the_suggestions_size(self):
        request = self.pending("ATTO")
        self.requests.fetch.return_value = request
        self.membership_service.summaries_for.return_value = [
            summary_of(DEFAULT_TENANCY, "Public")
        ]
        self.memberships.count.return_value = 4

        detail = self.service.detail(request.id)

        self.assertEqual(detail.id, request.id)
        self.assertEqual(
            detail.requester_tenancies, [summary_of(DEFAULT_TENANCY, "Public")]
        )
        self.assertEqual(detail.suggested_tenancy_members, 4)
        self.memberships.count.assert_called_once_with(ATTO)

    def test_without_a_suggestion_there_is_no_member_count(self):
        request = self.pending("Nothing like it")
        self.requests.fetch.return_value = request
        self.membership_service.summaries_for.return_value = []

        self.assertIsNone(self.service.detail(request.id).suggested_tenancy_members)

    def test_a_withdrawn_or_unknown_request_is_not_found(self):
        for found in (
            None,
            request_row(self.requester.id, status=TenancyRequestStatus.WITHDRAWN),
        ):
            with self.subTest(found=found):
                self.requests.fetch.return_value = found
                with self.assertRaises(NotFoundException) as raised:
                    self.service.detail(uuid4())
                self.assertEqual(str(raised.exception), "request_not_found")


class TestApprove(AdminQueueTestCase):
    def setUp(self):
        super().setUp()
        self.request = self.pending("ATTO")
        self.requests.fetch.return_value = self.request
        self.memberships.is_member.return_value = False
        self.event_id = uuid4()
        self.requests.approve.side_effect = (
            lambda request_id, admin_id, path, name, now: (
                request_row(
                    self.requester.id,
                    id=request_id,
                    status=TenancyRequestStatus.APPROVED,
                    tenancy=path,
                    created_tenancy=name is not None,
                    decided_by=admin_id,
                    decided_at=now,
                ),
                self.event_id,
            )
        )

    def code(self, tenancy=None, new_tenancy=None) -> str:
        with self.assertRaises(
            (IllegalStateException, ConflictException, NotFoundException)
        ) as raised:
            self.service.approve(self.request.id, self.admin.id, tenancy, new_tenancy)
        return str(raised.exception)

    def test_into_an_existing_tenancy(self):
        view = self.service.approve(self.request.id, self.admin.id, f" {ATTO} ", None)

        self.membership_service.require_open_for_members.assert_called_once_with(ATTO)
        self.requests.approve.assert_called_once_with(
            self.request.id, self.admin.id, ATTO, None, NOW
        )
        self.membership_service.announce_access.assert_called_once_with(
            self.requester.id, self.admin.id, ATTO, self.event_id
        )
        self.assertEqual(view.status, "approved")
        self.assertFalse(view.created_tenancy)
        self.assertEqual(view.decided_by.name, "Luciana Rizzo")

    def test_exactly_one_decision(self):
        self.assertEqual(self.code(), "invalid_request")
        self.assertEqual(
            self.code(ATTO, NewTenancy(display_name="X", namespace="x-1")),
            "invalid_request",
        )

    def test_a_second_decision_is_refused(self):
        self.request.status = TenancyRequestStatus.DECLINED

        self.assertEqual(self.code(ATTO), "request_not_pending")
        self.requests.approve.assert_not_called()

    def test_the_tenancy_rules_come_from_the_membership_service(self):
        self.membership_service.require_open_for_members.side_effect = (
            ConflictException("public_tenancy_locked")
        )

        self.assertEqual(self.code(DEFAULT_TENANCY), "public_tenancy_locked")

    def test_a_member_already_is_refused(self):
        self.memberships.is_member.return_value = True

        self.assertEqual(self.code(ATTO), "already_member")
        self.memberships.is_member.assert_called_once_with(self.requester.id, ATTO)

    def test_a_new_tenancy_needs_a_confirmed_email(self):
        self.membership_service.check_new_tenancy.return_value = (
            "datamap/production/atto-2",
            "ATTO 2",
        )
        self.requester.email_verified_at = None

        self.assertEqual(
            self.code(
                new_tenancy=NewTenancy(display_name="ATTO 2", namespace="atto-2")
            ),
            "requester_email_unverified",
        )
        self.requests.approve.assert_not_called()

    def test_a_new_tenancy_is_created_with_the_approval(self):
        self.membership_service.check_new_tenancy.return_value = (
            "datamap/production/atto-2",
            "ATTO 2",
        )

        view = self.service.approve(
            self.request.id,
            self.admin.id,
            None,
            NewTenancy(display_name="ATTO 2", namespace="atto-2"),
        )

        self.membership_service.check_new_tenancy.assert_called_once_with(
            "ATTO 2", "atto-2"
        )
        self.requests.approve.assert_called_once_with(
            self.request.id, self.admin.id, "datamap/production/atto-2", "ATTO 2", NOW
        )
        self.assertTrue(view.created_tenancy)


class TestDecline(AdminQueueTestCase):
    def setUp(self):
        super().setUp()
        self.request = self.pending("ATTO")
        self.requests.fetch.return_value = self.request
        self.requests.decline.side_effect = (
            lambda request_id, admin_id, message, now: request_row(
                self.requester.id,
                id=request_id,
                status=TenancyRequestStatus.DECLINED,
                decision_message=message,
                decided_by=admin_id,
                decided_at=now,
            )
        )

    def test_the_message_is_trimmed_and_the_requester_told(self):
        view = self.service.decline(self.request.id, self.admin.id, "  Ask Alan  ")

        self.requests.decline.assert_called_once_with(
            self.request.id, self.admin.id, "Ask Alan", NOW
        )
        self.assertEqual(view.decision_message, "Ask Alan")
        (user, declined), _ = self.notifier.request_declined.call_args
        self.assertIs(user, self.requester)
        self.assertEqual(declined.decision_message, "Ask Alan")

    def test_an_empty_message_is_null(self):
        self.service.decline(self.request.id, self.admin.id, "   ")
        self.service.decline(self.request.id, self.admin.id, None)

        messages = [c.args[2] for c in self.requests.decline.call_args_list]
        self.assertEqual(messages, [None, None])

    def test_a_message_over_1000_characters_is_refused(self):
        with self.assertRaises(IllegalStateException) as raised:
            self.service.decline(self.request.id, self.admin.id, "x" * 1001)

        self.assertEqual(str(raised.exception), "message_invalid")

    def test_a_second_decision_is_refused(self):
        self.request.status = TenancyRequestStatus.APPROVED

        with self.assertRaises(ConflictException) as raised:
            self.service.decline(self.request.id, self.admin.id, None)

        self.assertEqual(str(raised.exception), "request_not_pending")
