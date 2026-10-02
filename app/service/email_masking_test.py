import unittest

from app.service.email_masking import MASK, mask_secrets


class TestMaskSecrets(unittest.TestCase):
    def test_a_secret_is_masked_in_the_context_and_wherever_the_body_shows_it(self):
        link = "https://datamap.example/invitations/abc123"
        context = {"link": link, "dataset_name": "Rain"}
        body = f"Open {link} to accept. Again: {link}"

        masked_context, masked_body = mask_secrets(context, body, ["link"])

        self.assertEqual(masked_context, {"link": MASK, "dataset_name": "Rain"})
        self.assertEqual(masked_body, f"Open {MASK} to accept. Again: {MASK}")
        self.assertEqual(context["link"], link)

    def test_fields_that_are_not_secret_are_untouched(self):
        context = {"dataset_name": "Rain"}

        self.assertEqual(mask_secrets(context, "Rain", []), (context, "Rain"))

    def test_an_absent_or_empty_secret_masks_nothing_in_the_body(self):
        masked_context, masked_body = mask_secrets({"code": ""}, "body", ["code", "x"])

        self.assertEqual(masked_context, {"code": MASK})
        self.assertEqual(masked_body, "body")

    def test_a_secret_repeated_inside_other_fields_is_masked_there_too(self):
        context = {
            "code": "c0ffee12",
            "message": "Verification code: c0ffee12",
            "details": [{"label": "Code", "value": "c0ffee12"}],
            "count": 3,
        }

        masked_context, _ = mask_secrets(context, "", ["code"])

        self.assertEqual(
            masked_context,
            {
                "code": MASK,
                "message": f"Verification code: {MASK}",
                "details": [{"label": "Code", "value": MASK}],
                "count": 3,
            },
        )
