import hashlib
import unittest

from app.service.share_token import hash_token, new_token


class TestShareToken(unittest.TestCase):
    def test_tokens_are_long_and_distinct(self):
        tokens = {new_token() for _ in range(50)}
        self.assertEqual(len(tokens), 50)
        self.assertTrue(all(len(token) >= 43 for token in tokens))

    def test_the_hash_is_sha256_hex(self):
        self.assertEqual(hash_token("abc"), hashlib.sha256(b"abc").hexdigest())
