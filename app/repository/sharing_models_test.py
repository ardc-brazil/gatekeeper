import unittest

from app.model.db.sharing import (
    DatasetInvitation,
    DatasetAnonymousLink,
    DatasetAnonymousLinkView,
)


class TestSharingTables(unittest.TestCase):
    def test_invitation_table_has_the_columns_the_rfc_names(self):
        self.assertEqual(
            set(DatasetInvitation.__table__.columns.keys()),
            {
                "id",
                "dataset_id",
                "email",
                "orcid",
                "level",
                "token_hash",
                "invited_by",
                "accepted_at",
                "accepted_by",
                "revoked_at",
                "created_at",
            },
        )

    def test_anonymous_link_tables_record_no_reviewer_identity(self):
        self.assertEqual(
            set(DatasetAnonymousLinkView.__table__.columns.keys()),
            {"id", "link_id", "outcome", "viewed_at"},
        )
        self.assertNotIn("expires_at", DatasetAnonymousLink.__table__.columns.keys())

    def test_tokens_are_unique(self):
        self.assertTrue(DatasetInvitation.__table__.c.token_hash.unique)
        self.assertTrue(DatasetAnonymousLink.__table__.c.token_hash.unique)
