import unittest

from jinja2 import UndefinedError

from app.service.email_template import EmailTemplate, EmailTemplateRenderer

SITE_URL = "https://datamap.example.org/"

CONTEXTS = {
    EmailTemplate.INVITATION: {
        "inviter_name": "Maria Oliveira",
        "inviter_email": "maria.oliveira@usp.br",
        "workspace_name": "Data Amazon",
        "role": "Contributor — can upload and edit datasets",
        "expires_on": "October 14, 2026",
        "accept_url": "https://datamap.example.org/account/login?invite=8f3a2c&tenancy=a/b",
    },
    EmailTemplate.ANNOUNCEMENT: {
        "title": "Notebooks are now available in DataMap",
        "preheader": "Notebooks are now available.",
        "published_on": "September 30, 2026",
        "body": "You can now open any dataset in a notebook.",
        "highlights": ["Start a notebook from any dataset page."],
        "cta_label": "Read the announcement",
        "cta_url": "https://datamap.example.org/news/notebooks",
    },
    EmailTemplate.DATASET_REMINDER: {
        "dataset_title": "GoAmazon 2014/5 — Aerosol size distribution",
        "draft_days": 21,
        "status": "Draft",
        "last_updated_on": "September 9, 2026",
        "files_summary": "14 files · 2.3 GB",
        "missing_fields": ["License", "Contact person"],
        "complete_url": "https://datamap.example.org/datasets/3f9c1e/edit",
        "snooze_url": "https://datamap.example.org/datasets/3f9c1e/reminders",
    },
    EmailTemplate.NOTIFICATION: {
        "title": "Your access request was approved",
        "preheader": "You now have access to Manaus Radar Reflectivity 2023.",
        "actor_name": "André Maia",
        "message": "approved your request.",
        "details": [{"label": "Dataset", "value": "Manaus Radar Reflectivity 2023"}],
        "cta_label": "Open dataset",
        "cta_url": "https://datamap.example.org/datasets/7b21d4",
        "reason": "You received this email because you requested access to a dataset.",
    },
}


class TestEmailTemplateRenderer(unittest.TestCase):
    def setUp(self):
        self.renderer = EmailTemplateRenderer(site_url=SITE_URL)

    def test_every_template_renders_with_its_context(self):
        for template in EmailTemplate:
            with self.subTest(template=template):
                email = self.renderer.render(template, CONTEXTS[template])

                self.assertTrue(email.html.startswith("<!DOCTYPE html>"))
                self.assertNotIn("{{", email.html)
                self.assertNotIn("{%", email.html)
                self.assertTrue(email.subject)

    def test_assets_and_footer_links_are_absolute_to_the_site(self):
        email = self.renderer.render(
            EmailTemplate.INVITATION, CONTEXTS[EmailTemplate.INVITATION]
        )

        self.assertIn(
            'src="https://datamap.example.org/img/email/datamap-tile-36.png"',
            email.html,
        )
        self.assertIn('href="https://datamap.example.org/project/about"', email.html)

    def test_no_template_links_to_preferences_or_unsubscribe(self):
        for template in EmailTemplate:
            with self.subTest(template=template):
                html = self.renderer.render(template, CONTEXTS[template]).html.lower()

                self.assertNotIn("unsubscribe", html)
                self.assertNotIn("preferences", html)
                self.assertNotIn('href="https://datamap.example.org/profile"', html)

    def test_footer_datasets_link_points_to_the_dataset_list(self):
        for template in EmailTemplate:
            with self.subTest(template=template):
                html = self.renderer.render(template, CONTEXTS[template]).html

                self.assertIn('href="https://datamap.example.org/app/datasets"', html)
                self.assertNotIn('href="https://datamap.example.org/datasets"', html)

    def test_context_values_are_substituted(self):
        email = self.renderer.render(
            EmailTemplate.INVITATION, CONTEXTS[EmailTemplate.INVITATION]
        )

        self.assertIn("You&#39;ve been invited to join Data Amazon", email.html)
        self.assertIn("maria.oliveira@usp.br", email.html)
        self.assertIn("October 14, 2026", email.html)

    def test_url_query_strings_are_attribute_escaped(self):
        email = self.renderer.render(
            EmailTemplate.INVITATION, CONTEXTS[EmailTemplate.INVITATION]
        )

        self.assertIn("invite=8f3a2c&amp;tenancy=a/b", email.html)

    def test_user_supplied_values_are_html_escaped(self):
        context = {
            **CONTEXTS[EmailTemplate.INVITATION],
            "inviter_name": "<script>alert(1)</script>",
        }

        email = self.renderer.render(EmailTemplate.INVITATION, context)

        self.assertNotIn("<script>", email.html)
        self.assertIn("&lt;script&gt;", email.html)

    def test_subject_comes_from_the_title_block(self):
        email = self.renderer.render(
            EmailTemplate.ANNOUNCEMENT, CONTEXTS[EmailTemplate.ANNOUNCEMENT]
        )

        self.assertEqual(email.subject, "Notebooks are now available in DataMap")

    def test_a_missing_required_variable_raises(self):
        context = dict(CONTEXTS[EmailTemplate.INVITATION])
        del context["accept_url"]

        with self.assertRaises(UndefinedError):
            self.renderer.render(EmailTemplate.INVITATION, context)

    def test_optional_sections_are_left_out_when_not_given(self):
        context = {
            key: value
            for key, value in CONTEXTS[EmailTemplate.DATASET_REMINDER].items()
            if key != "missing_fields"
        }

        email = self.renderer.render(EmailTemplate.DATASET_REMINDER, context)

        self.assertNotIn("Missing before publication", email.html)

    def test_missing_fields_are_listed(self):
        email = self.renderer.render(
            EmailTemplate.DATASET_REMINDER, CONTEXTS[EmailTemplate.DATASET_REMINDER]
        )

        self.assertIn("Missing before publication", email.html)
        self.assertIn("Contact person", email.html)

    def test_announcement_image_is_rendered_only_when_given(self):
        without = self.renderer.render(
            EmailTemplate.ANNOUNCEMENT, CONTEXTS[EmailTemplate.ANNOUNCEMENT]
        )
        with_image = self.renderer.render(
            EmailTemplate.ANNOUNCEMENT,
            {
                **CONTEXTS[EmailTemplate.ANNOUNCEMENT],
                "image_url": "https://cdn.example.org/notebooks.png",
                "image_alt": "Notebook screenshot",
            },
        )

        self.assertNotIn("cdn.example.org", without.html)
        self.assertIn('src="https://cdn.example.org/notebooks.png"', with_image.html)
