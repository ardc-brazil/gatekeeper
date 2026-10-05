import unittest
from unittest.mock import MagicMock
from uuid import uuid4

from app.exception.conflict import ConflictException
from app.model.tenancy import DEFAULT_TENANCY
from app.repository.tenancy_membership import TenancyMembershipRepository


class TestRemove(unittest.TestCase):
    def test_nobody_is_ever_removed_from_the_public_tenancy(self):
        session_factory = MagicMock()

        with self.assertRaises(ConflictException) as raised:
            TenancyMembershipRepository(session_factory).remove(
                DEFAULT_TENANCY, uuid4(), uuid4()
            )

        self.assertEqual(str(raised.exception), "public_tenancy_locked")
        session_factory.assert_not_called()
