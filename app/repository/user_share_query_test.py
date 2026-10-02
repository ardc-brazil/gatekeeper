import unittest

from app.repository.user import like_pattern


class TestLikePattern(unittest.TestCase):
    def test_the_term_is_wrapped_for_a_contains_match(self):
        self.assertEqual(like_pattern("ana"), "%ana%")

    def test_wildcards_typed_by_the_user_are_escaped(self):
        self.assertEqual(like_pattern("50%_a\\b"), "%50\\%\\_a\\\\b%")

    def test_surrounding_spaces_are_ignored(self):
        self.assertEqual(like_pattern("  ana "), "%ana%")
