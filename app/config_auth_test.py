import os
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from app.config import Config
from app.config_email_test import REQUIRED


class TestAuthSettings(unittest.TestCase):
    def build(self, **overrides) -> Config:
        with patch.dict(os.environ, {**REQUIRED, **overrides}, clear=True):
            return Config(_env_file=None)

    def without(self, key: str) -> Config:
        values = {name: value for name, value in REQUIRED.items() if name != key}
        with patch.dict(os.environ, values, clear=True):
            return Config(_env_file=None)

    def test_both_peppers_are_read_as_written(self):
        config = self.build()

        self.assertEqual(config.AUTH_PASSWORD_PEPPER, "password-pepper-of-sixteen")
        self.assertEqual(config.AUTH_CHALLENGE_PEPPER, "challenge-pepper-of-sixteen")

    def test_the_application_does_not_start_without_a_password_pepper(self):
        with self.assertRaises(ValidationError):
            self.without("AUTH_PASSWORD_PEPPER")

    def test_the_application_does_not_start_without_a_challenge_pepper(self):
        with self.assertRaises(ValidationError):
            self.without("AUTH_CHALLENGE_PEPPER")

    def test_a_pepper_shorter_than_sixteen_characters_is_refused(self):
        for key in ("AUTH_PASSWORD_PEPPER", "AUTH_CHALLENGE_PEPPER"):
            with self.subTest(key=key), self.assertRaises(ValidationError):
                self.build(**{key: "fifteen-chars-x"})

    def test_admin_notifications_are_off_unless_configured(self):
        self.assertEqual(self.build().ADMIN_NOTIFICATION_EMAILS, "")

    def test_the_admin_list_is_kept_as_written(self):
        config = self.build(ADMIN_NOTIFICATION_EMAILS="a@usp.br, b@usp.br")

        self.assertEqual(config.ADMIN_NOTIFICATION_EMAILS, "a@usp.br, b@usp.br")
