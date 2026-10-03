import unittest
from unittest.mock import patch

from app.service.password import (
    BCRYPT_ROUNDS,
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    PasswordHasher,
    password_is_acceptable,
)

PEPPER = "password-pepper-of-sixteen"
FAST = 4


class TestPasswordHasher(unittest.TestCase):
    def setUp(self):
        self.hasher = PasswordHasher(pepper=PEPPER, rounds=FAST)

    def test_a_hashed_password_verifies(self):
        stored = self.hasher.hash("correct horse battery")

        self.assertTrue(self.hasher.verify("correct horse battery", stored))

    def test_a_different_password_does_not_verify(self):
        stored = self.hasher.hash("correct horse battery")

        self.assertFalse(self.hasher.verify("correct horse batterz", stored))

    def test_the_same_password_hashes_differently_each_time(self):
        self.assertNotEqual(
            self.hasher.hash("correct horse battery"),
            self.hasher.hash("correct horse battery"),
        )

    def test_a_hash_is_useless_without_its_pepper(self):
        stored = self.hasher.hash("correct horse battery")
        other = PasswordHasher(pepper="another-pepper-of-sixteen", rounds=FAST)

        self.assertFalse(other.verify("correct horse battery", stored))

    def test_the_hash_is_bcrypt_at_cost_ten_by_default(self):
        stored = PasswordHasher(pepper=PEPPER).hash("correct horse battery")

        self.assertEqual(BCRYPT_ROUNDS, 10)
        self.assertTrue(stored.startswith("$2b$10$"))
        self.assertEqual(len(stored), 60)

    def test_passwords_longer_than_what_bcrypt_reads_are_still_told_apart(self):
        prefix = "x" * 100
        stored = self.hasher.hash(prefix + "a")

        self.assertFalse(self.hasher.verify(prefix + "b", stored))

    def test_a_stored_value_of_another_shape_is_refused_without_reaching_bcrypt(self):
        for stored in ("", "$2b$10$short", "hmac-sha256$abc"):
            with self.subTest(stored=stored):
                self.assertFalse(self.hasher.verify("correct horse battery", stored))

    def test_burning_a_check_runs_bcrypt_once(self):
        with patch(
            "app.service.password.bcrypt.checkpw", return_value=False
        ) as checkpw:
            self.assertIsNone(self.hasher.burn("whatever was typed"))

        checkpw.assert_called_once()

    def test_a_short_pepper_is_refused(self):
        with self.assertRaises(ValueError):
            PasswordHasher(pepper="fifteen-chars-x")


class TestPasswordPolicy(unittest.TestCase):
    def test_ten_to_one_hundred_and_twenty_eight_characters_are_accepted(self):
        self.assertEqual((MIN_PASSWORD_LENGTH, MAX_PASSWORD_LENGTH), (10, 128))
        self.assertTrue(password_is_acceptable("a" * 10))
        self.assertTrue(password_is_acceptable("a" * 128))

    def test_shorter_or_longer_is_refused(self):
        self.assertFalse(password_is_acceptable("a" * 9))
        self.assertFalse(password_is_acceptable("a" * 129))
        self.assertFalse(password_is_acceptable(""))

    def test_no_composition_rule_applies(self):
        self.assertTrue(password_is_acceptable("aaaaaaaaaa"))
        self.assertTrue(password_is_acceptable("só letras e espaços"))
