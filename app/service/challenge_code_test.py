import hashlib
import hmac
import unittest
from unittest.mock import patch
from uuid import UUID

from app.service.challenge_code import CODE_LENGTH, code_hash, new_code

PEPPER = "challenge-pepper-of-sixteen"
CHALLENGE = UUID("6f1c2b8e-0d1a-4c55-9a43-2f6f0a1b9c11")
OTHER_CHALLENGE = UUID("0b7d4d3a-8f33-4f0e-9a8c-6c2a4f1e7d20")


class TestNewCode(unittest.TestCase):
    def test_a_code_is_six_digits(self):
        self.assertEqual(CODE_LENGTH, 6)
        for _ in range(1000):
            self.assertRegex(new_code(), r"^\d{6}$")

    def test_codes_are_drawn_from_the_whole_million(self):
        with patch(
            "app.service.challenge_code.secrets.randbelow", return_value=0
        ) as draw:
            self.assertEqual(new_code(), "000000")
        draw.assert_called_once_with(1_000_000)

        with patch(
            "app.service.challenge_code.secrets.randbelow", return_value=999_999
        ):
            self.assertEqual(new_code(), "999999")

    def test_leading_zeros_are_kept(self):
        with patch("app.service.challenge_code.secrets.randbelow", return_value=42):
            self.assertEqual(new_code(), "000042")


class TestCodeHash(unittest.TestCase):
    def test_it_is_hmac_sha256_of_the_challenge_id_followed_by_the_code(self):
        expected = hmac.new(
            PEPPER.encode("utf-8"),
            f"{CHALLENGE}123456".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        self.assertEqual(code_hash(PEPPER, CHALLENGE, "123456"), expected)
        self.assertRegex(expected, r"^[0-9a-f]{64}$")

    def test_the_same_code_on_another_challenge_hashes_differently(self):
        self.assertNotEqual(
            code_hash(PEPPER, CHALLENGE, "123456"),
            code_hash(PEPPER, OTHER_CHALLENGE, "123456"),
        )

    def test_another_pepper_hashes_differently(self):
        self.assertNotEqual(
            code_hash(PEPPER, CHALLENGE, "123456"),
            code_hash("another-pepper-of-sixteen", CHALLENGE, "123456"),
        )

    def test_another_code_hashes_differently(self):
        self.assertNotEqual(
            code_hash(PEPPER, CHALLENGE, "123456"),
            code_hash(PEPPER, CHALLENGE, "123457"),
        )

    def test_a_short_pepper_is_refused(self):
        with self.assertRaises(ValueError):
            code_hash("fifteen-chars-x", CHALLENGE, "123456")
