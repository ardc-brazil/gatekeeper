import unittest

from app.service.redaction import redact_metadata


class TestRedaction(unittest.TestCase):
    def test_authorship_is_redacted_and_keeps_its_shape(self):
        data = {
            "authors": [{"name": "Ana"}, {"name": "Bruno"}, {"name": "Carla"}],
            "owner": {"name": "Ana"},
            "institution": "USP",
            "citation": {"doi": "10.1234/abc"},
            "colaborators": [{"name": "Davi", "permission": "can_view"}],
        }

        redacted = redact_metadata(data)

        self.assertEqual(
            redacted["authors"],
            [{"name": "[redacted]"}, {"name": "[redacted]"}, {"name": "[redacted]"}],
        )
        self.assertEqual(redacted["owner"], {"name": "[redacted]"})
        self.assertEqual(redacted["institution"], "[redacted]")
        self.assertEqual(redacted["citation"], {"doi": "[redacted]"})
        self.assertEqual(
            redacted["colaborators"],
            [{"name": "[redacted]", "permission": "[redacted]"}],
        )

    def test_allowlisted_fields_pass_through(self):
        data = {"description": "Ozone at ATTO", "tags": ["ozone"], "is_enabled": True}
        self.assertEqual(redact_metadata(data), data)

    def test_an_unknown_field_is_redacted(self):
        self.assertEqual(redact_metadata({"pi_name": "Ana"}), {"pi_name": "[redacted]"})

    def test_non_strings_inside_a_redacted_field_are_kept(self):
        self.assertEqual(
            redact_metadata({"project": {"code": "AF", "year": 2026}}),
            {"project": {"code": "[redacted]", "year": 2026}},
        )

    def test_missing_metadata_is_an_empty_dict(self):
        self.assertEqual(redact_metadata(None), {})
