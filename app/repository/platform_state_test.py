import unittest

from app.model.dataset import DesignState, VisibilityStatus
from app.repository.platform_state import label


class TestLabels(unittest.TestCase):
    def test_an_enum_is_labelled_by_its_name_not_its_value(self):
        self.assertEqual(label(VisibilityStatus.PUBLIC), "PUBLIC")
        self.assertEqual(label(DesignState.PUBLISHED), "PUBLISHED")

    def test_a_missing_value_is_labelled_none(self):
        self.assertEqual(label(None), "none")

    def test_anything_else_becomes_a_string(self):
        self.assertEqual(label(2), "2")
