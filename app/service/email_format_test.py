import unittest
from datetime import date, datetime, timezone

from app.service.email_format import (
    first_name,
    long_date,
    short_date,
    tenancy_display_name,
)


class TestEmailFormat(unittest.TestCase):
    def test_dates_read_as_the_design_writes_them(self):
        moment = datetime(2026, 12, 5, 23, 59, tzinfo=timezone.utc)
        self.assertEqual(long_date(moment), "December 5, 2026")
        self.assertEqual(short_date(moment), "December 5")
        self.assertEqual(long_date(date(2026, 1, 15)), "January 15, 2026")

    def test_a_tenancy_is_named_by_its_last_segment(self):
        self.assertEqual(
            tenancy_display_name("datamap/production/data-amazon"), "Data Amazon"
        )
        self.assertEqual(tenancy_display_name("goamazon"), "Goamazon")
        self.assertEqual(tenancy_display_name(None), "the workspace")

    def test_a_first_name_is_the_first_word(self):
        self.assertEqual(first_name("Luciana Varanda Rizzo"), "Luciana")
        self.assertEqual(first_name("  Ana  "), "Ana")
        self.assertEqual(first_name(""), "")
