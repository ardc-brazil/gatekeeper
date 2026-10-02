import unittest

from app.exception.bad_request import BadRequestException
from app.service.share_identity import (
    normalise_email,
    normalise_orcid,
    orcid_checksum_ok,
)


class TestEmail(unittest.TestCase):
    def test_an_email_is_trimmed_and_lowercased(self):
        self.assertEqual(normalise_email("  Ana.Silva@USP.br "), "ana.silva@usp.br")

    def test_a_value_without_a_domain_is_refused(self):
        with self.assertRaises(BadRequestException) as caught:
            normalise_email("ana.silva")
        self.assertEqual(caught.exception.errors[0].code, "invalid_email")


class TestOrcid(unittest.TestCase):
    def test_the_bare_form_is_accepted(self):
        self.assertEqual(normalise_orcid("0000-0002-1825-0097"), "0000-0002-1825-0097")

    def test_the_url_form_is_reduced_to_the_bare_form(self):
        self.assertEqual(
            normalise_orcid("https://orcid.org/0000-0002-1825-0097"),
            "0000-0002-1825-0097",
        )

    def test_dashes_are_restored_and_a_lowercase_x_is_raised(self):
        self.assertEqual(normalise_orcid("000000021694233x"), "0000-0002-1694-233X")

    def test_a_wrong_check_digit_is_refused(self):
        with self.assertRaises(BadRequestException) as caught:
            normalise_orcid("0000-0002-1825-0098")
        self.assertEqual(caught.exception.errors[0].code, "invalid_orcid")

    def test_a_malformed_value_is_refused(self):
        with self.assertRaises(BadRequestException):
            normalise_orcid("orcid:1234")

    def test_checksum_examples(self):
        self.assertTrue(orcid_checksum_ok("0000-0001-5109-3700"))
        self.assertTrue(orcid_checksum_ok("0000-0002-1694-233X"))
        self.assertFalse(orcid_checksum_ok("0000-0001-5109-3701"))
