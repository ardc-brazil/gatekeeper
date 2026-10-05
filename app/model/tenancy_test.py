import unittest

from app.model.tenancy import (
    DEFAULT_TENANCY,
    TenancyEventType,
    TenancyInvitationStatus,
    TenancyRequestStatus,
    derived_display_name,
    display_name_of,
    is_default,
    is_legacy,
    is_production,
    match_key,
    namespace_is_valid,
    namespace_of,
    summary_of,
    tenancy_order,
    trimmed_within,
)
from app.model.user import DEFAULT_ROLE
from app.service.email_format import tenancy_display_name


class TestPaths(unittest.TestCase):
    def test_the_default_tenancy_is_public_in_production(self):
        self.assertEqual(DEFAULT_TENANCY, "datamap/production/public")
        self.assertTrue(is_default(DEFAULT_TENANCY))
        self.assertFalse(is_default("datamap/production/atto"))

    def test_staging_is_legacy_and_not_production(self):
        self.assertTrue(is_legacy("datamap/staging/data-amazon"))
        self.assertFalse(is_production("datamap/staging/data-amazon"))
        self.assertTrue(is_production("datamap/production/data-amazon"))
        self.assertFalse(is_legacy("datamap/production/data-amazon"))

    def test_the_namespace_is_the_last_segment(self):
        self.assertEqual(
            namespace_of("datamap/production/cerrado-flux"), "cerrado-flux"
        )


class TestDisplayNames(unittest.TestCase):
    def test_the_column_wins(self):
        self.assertEqual(display_name_of("datamap/production/atto", "ATTO"), "ATTO")

    def test_without_the_column_the_namespace_is_title_cased(self):
        self.assertEqual(
            display_name_of("datamap/production/lba-legacy", None), "Lba Legacy"
        )
        self.assertEqual(
            derived_display_name("datamap/staging/data_amazon"), "Data Amazon"
        )

    def test_an_empty_column_falls_back_too(self):
        self.assertEqual(display_name_of("datamap/production/atto", ""), "Atto")

    def test_the_email_helper_uses_the_same_rule(self):
        self.assertEqual(
            tenancy_display_name("datamap/production/data-amazon"), "Data Amazon"
        )
        self.assertEqual(tenancy_display_name(None), "the workspace")

    def test_a_summary_flags_public_and_legacy(self):
        self.assertEqual(
            summary_of(DEFAULT_TENANCY, "Public"),
            summary_of(DEFAULT_TENANCY, "Public"),
        )
        public = summary_of(DEFAULT_TENANCY, "Public")
        legacy = summary_of("datamap/staging/data-amazon", None)
        self.assertTrue(public.is_default)
        self.assertFalse(public.is_legacy)
        self.assertTrue(legacy.is_legacy)
        self.assertEqual(legacy.display_name, "Data Amazon")


class TestOrder(unittest.TestCase):
    def test_public_then_production_by_name_then_legacy_by_path(self):
        rows = [
            ("datamap/staging/b", "B"),
            ("datamap/production/zeta", "zeta"),
            (DEFAULT_TENANCY, "Public"),
            ("datamap/staging/a", "Z"),
            ("datamap/production/alpha", "Alpha"),
        ]

        ordered = [path for path, name in sorted(rows, key=lambda r: tenancy_order(*r))]

        self.assertEqual(
            ordered,
            [
                DEFAULT_TENANCY,
                "datamap/production/alpha",
                "datamap/production/zeta",
                "datamap/staging/a",
                "datamap/staging/b",
            ],
        )


class TestMatching(unittest.TestCase):
    def test_case_and_spaces_versus_hyphens_do_not_matter(self):
        self.assertEqual(match_key("Cerrado Flux"), match_key("cerrado-flux"))
        self.assertEqual(match_key("  LBA   legacy "), match_key("lba-legacy"))

    def test_different_names_do_not_match(self):
        self.assertNotEqual(match_key("ATTO"), match_key("ATTO tower"))


class TestValidation(unittest.TestCase):
    def test_a_namespace_is_lower_case_digits_and_hyphens(self):
        for valid in ("atto", "lba-legacy", "a1", "x" * 63):
            with self.subTest(valid=valid):
                self.assertTrue(namespace_is_valid(valid))
        for invalid in (
            "a",
            "x" * 64,
            "Atto",
            "lba legacy",
            "lba_legacy",
            "public",
            "",
            "atto\n",
            "atto\r",
        ):
            with self.subTest(invalid=invalid):
                self.assertFalse(namespace_is_valid(invalid))

    def test_trimmed_within_trims_and_checks_the_length(self):
        self.assertEqual(trimmed_within("  ATTO  ", 1, 128), "ATTO")
        self.assertIsNone(trimmed_within("   ", 1, 128))
        self.assertIsNone(trimmed_within(None, 1, 128))
        self.assertIsNone(trimmed_within("x" * 129, 1, 128))
        self.assertEqual(trimmed_within("", 0, 1000), "")


class TestEnums(unittest.TestCase):
    def test_the_values_the_rfc_names(self):
        self.assertEqual(
            [s.value for s in TenancyRequestStatus],
            ["pending", "approved", "declined", "withdrawn"],
        )
        self.assertEqual(
            [s.value for s in TenancyInvitationStatus],
            ["pending", "accepted", "declined", "withdrawn", "revoked"],
        )
        self.assertEqual(
            [s.value for s in TenancyEventType],
            [
                "tenancy_created",
                "member_added",
                "member_removed",
                "request_created",
                "request_approved",
                "request_declined",
                "request_withdrawn",
                "invitation_created",
                "invitation_accepted",
                "invitation_declined",
                "invitation_withdrawn",
            ],
        )

    def test_every_new_account_gets_datasets_write(self):
        self.assertEqual(DEFAULT_ROLE, "datasets_write")
