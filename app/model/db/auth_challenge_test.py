import unittest

from app.model.auth_challenge import ChallengeKind
from app.model.db.auth_challenge import AuthChallenge
from app.model.db.user import User


class TestAuthChallengeTable(unittest.TestCase):
    def test_it_has_the_columns_the_rfc_names_and_the_issue_time(self):
        self.assertEqual(
            set(AuthChallenge.__table__.columns.keys()),
            {
                "id",
                "kind",
                "email",
                "secret_hash",
                "attempts",
                "expires_at",
                "consumed_at",
                "confirmed_at",
                "issued_at",
                "user_id",
                "payload",
                "created_at",
            },
        )

    def test_a_secret_hash_is_unique(self):
        self.assertTrue(AuthChallenge.__table__.c.secret_hash.unique)

    def test_a_challenge_goes_away_with_its_user(self):
        (foreign_key,) = AuthChallenge.__table__.c.user_id.foreign_keys

        self.assertEqual(foreign_key.column.table.name, "users")
        self.assertEqual(foreign_key.ondelete, "CASCADE")
        self.assertTrue(AuthChallenge.__table__.c.user_id.nullable)

    def test_only_consumption_confirmation_and_the_user_are_optional(self):
        columns = AuthChallenge.__table__.c
        optional = {column.name for column in columns if column.nullable}

        self.assertEqual(optional, {"consumed_at", "confirmed_at", "user_id"})

    def test_the_kinds_are_the_three_flows(self):
        self.assertEqual(
            {kind.value for kind in ChallengeKind},
            {"sign_up", "email_verification", "password_reset"},
        )


class TestUserCredentialColumns(unittest.TestCase):
    def test_users_carry_a_password_a_confirmation_and_a_lock(self):
        self.assertTrue(
            {
                "password_hash",
                "email_verified_at",
                "failed_login_count",
                "locked_until",
            }
            <= set(User.__table__.columns.keys())
        )

    def test_only_the_failure_count_is_required(self):
        columns = User.__table__.c

        self.assertTrue(columns.password_hash.nullable)
        self.assertTrue(columns.email_verified_at.nullable)
        self.assertTrue(columns.locked_until.nullable)
        self.assertFalse(columns.failed_login_count.nullable)
        self.assertEqual(columns.failed_login_count.server_default.arg, "0")

    def test_a_password_hash_column_holds_a_bcrypt_hash(self):
        self.assertEqual(User.__table__.c.password_hash.type.length, 128)
