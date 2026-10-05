import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.exception.conflict import ConflictException
from app.model.tenancy import TenancyRequestStatus
from app.repository.integrity import violates
from app.repository.tenancy import TenancyRepository
from app.repository.tenancy_invitation import TenancyInvitationRepository
from app.repository.tenancy_request import TenancyRequestRepository


def integrity_error(constraint: str | None) -> IntegrityError:
    return IntegrityError(
        "INSERT", {}, SimpleNamespace(diag=SimpleNamespace(constraint_name=constraint))
    )


class FailingFlush:
    def __init__(self, constraint: str | None) -> None:
        self.session = MagicMock()
        self.session.flush.side_effect = integrity_error(constraint)
        locked = self.session.query.return_value.filter_by.return_value
        locked.with_for_update.return_value.first.return_value = SimpleNamespace(
            id=uuid4(), user_id=uuid4(), status=TenancyRequestStatus.PENDING
        )

    @contextmanager
    def __call__(self):
        yield self.session


class TestViolates(unittest.TestCase):
    def test_only_the_named_constraint_matches(self):
        error = integrity_error("uq_tenancy_requests_pending")

        self.assertTrue(violates(error, "uq_tenancy_requests_pending"))
        self.assertFalse(violates(error, "tenancies_pkey"))

    def test_an_error_without_diagnostics_matches_nothing(self):
        error = IntegrityError("INSERT", {}, Exception("unique"))

        self.assertFalse(violates(error, "tenancies_pkey"))


CASES = (
    (
        "tenancy created with its event",
        "tenancies_pkey",
        "tenancy_exists",
        lambda factory: TenancyRepository(factory).create_with_event(
            "datamap/production/atto", "ATTO", uuid4()
        ),
    ),
    (
        "tenancy request",
        "uq_tenancy_requests_pending",
        "request_pending",
        lambda factory: TenancyRequestRepository(factory).create(
            uuid4(), "ATTO", "Fluxes"
        ),
    ),
    (
        "approval creating a tenancy",
        "tenancies_pkey",
        "tenancy_exists",
        lambda factory: TenancyRequestRepository(factory).approve(
            uuid4(), uuid4(), "datamap/production/atto", "ATTO", None
        ),
    ),
    (
        "tenancy invitation",
        "uq_tenancy_invitations_pending",
        "invitation_pending",
        lambda factory: TenancyInvitationRepository(factory).create(
            "datamap/production/atto", uuid4(), uuid4(), None
        ),
    ),
)


class TestConflictsAreMappedByConstraint(unittest.TestCase):
    def test_the_expected_constraint_is_a_conflict(self):
        for name, constraint, code, call in CASES:
            with self.subTest(name):
                with self.assertRaises(ConflictException) as raised:
                    call(FailingFlush(constraint))
                self.assertEqual(str(raised.exception), code)

    def test_any_other_integrity_error_is_raised_as_is(self):
        for name, _, _, call in CASES:
            with self.subTest(name):
                with self.assertRaises(IntegrityError):
                    call(FailingFlush("tenancy_events_tenancy_fkey"))
