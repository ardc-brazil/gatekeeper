import unittest
from datetime import datetime, timedelta, timezone

from app.model.embargo import MAX_EMBARGO_PERIOD, REMINDER_OFFSETS_DAYS, embargo_active

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class TestEmbargoActive(unittest.TestCase):
    def test_no_date_is_no_embargo(self):
        self.assertFalse(embargo_active(None, NOW))

    def test_a_future_date_is_an_active_embargo(self):
        self.assertTrue(embargo_active(NOW + timedelta(seconds=1), NOW))

    def test_a_date_that_has_passed_is_no_longer_an_embargo(self):
        self.assertFalse(embargo_active(NOW, NOW))
        self.assertFalse(embargo_active(NOW - timedelta(days=1), NOW))


class TestConstants(unittest.TestCase):
    def test_the_cap_is_ninety_days(self):
        self.assertEqual(MAX_EMBARGO_PERIOD, timedelta(days=90))

    def test_reminders_are_fifteen_ten_five_and_one_day_before(self):
        self.assertEqual(REMINDER_OFFSETS_DAYS, (15, 10, 5, 1))
