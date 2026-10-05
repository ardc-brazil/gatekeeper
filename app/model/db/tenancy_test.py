import unittest

from app.model.db.dataset import Dataset
from app.model.db.tenancy import (
    Tenancy,
    TenancyEvent,
    TenancyInvitation,
    TenancyRequest,
)
from app.model.dataset import Dataset as DatasetModel


def _indexes(table) -> dict:
    return {index.name: index for index in table.indexes}


class TestTenancyTable(unittest.TestCase):
    def test_a_display_name_is_optional_and_short(self):
        column = Tenancy.__table__.c.display_name
        self.assertTrue(column.nullable)
        self.assertEqual(column.type.length, 64)


class TestRequestTable(unittest.TestCase):
    def test_it_has_the_columns_the_rfc_names(self):
        self.assertEqual(
            set(TenancyRequest.__table__.columns.keys()),
            {
                "id",
                "user_id",
                "requested_name",
                "reason",
                "status",
                "tenancy",
                "created_tenancy",
                "decision_message",
                "decided_by",
                "decided_at",
                "created_at",
                "updated_at",
            },
        )

    def test_one_pending_request_per_user_is_an_index(self):
        index = _indexes(TenancyRequest.__table__)["uq_tenancy_requests_pending"]
        self.assertTrue(index.unique)
        self.assertEqual([c.name for c in index.columns], ["user_id"])
        self.assertEqual(
            str(index.dialect_options["postgresql"]["where"]), "status = 'pending'"
        )
        self.assertIn(
            "ix_tenancy_requests_status_created", _indexes(TenancyRequest.__table__)
        )

    def test_a_request_goes_away_with_its_user(self):
        (foreign_key,) = TenancyRequest.__table__.c.user_id.foreign_keys
        self.assertEqual(foreign_key.ondelete, "CASCADE")
        (decider,) = TenancyRequest.__table__.c.decided_by.foreign_keys
        self.assertEqual(decider.ondelete, "SET NULL")


class TestInvitationTable(unittest.TestCase):
    def test_it_has_the_columns_the_rfc_names(self):
        self.assertEqual(
            set(TenancyInvitation.__table__.columns.keys()),
            {
                "id",
                "tenancy",
                "user_id",
                "invited_by",
                "dataset_id",
                "status",
                "closed_by",
                "closed_at",
                "created_at",
                "updated_at",
            },
        )

    def test_one_pending_invitation_per_user_and_tenancy(self):
        index = _indexes(TenancyInvitation.__table__)["uq_tenancy_invitations_pending"]
        self.assertTrue(index.unique)
        self.assertEqual([c.name for c in index.columns], ["tenancy", "user_id"])
        self.assertIn(
            "ix_tenancy_invitations_user_status", _indexes(TenancyInvitation.__table__)
        )

    def test_the_dataset_it_came_from_may_disappear(self):
        (foreign_key,) = TenancyInvitation.__table__.c.dataset_id.foreign_keys
        self.assertEqual(foreign_key.ondelete, "SET NULL")


class TestEventTable(unittest.TestCase):
    def test_user_ids_and_tenancy_are_not_foreign_keys(self):
        table = TenancyEvent.__table__
        for name in ("tenancy", "user_id", "actor_id", "request_id", "invitation_id"):
            with self.subTest(column=name):
                self.assertEqual(table.c[name].foreign_keys, set())
                self.assertTrue(table.c[name].nullable)
        self.assertEqual(
            set(_indexes(table)),
            {"ix_tenancy_events_created", "ix_tenancy_events_user"},
        )


class TestDatasetDefault(unittest.TestCase):
    def test_new_datasets_are_closed_to_members(self):
        column = Dataset.__table__.c.members_can_edit
        self.assertFalse(column.default.arg)
        self.assertEqual(str(column.server_default.arg), "false")
        self.assertFalse(DatasetModel(name="d", data={}).members_can_edit)
