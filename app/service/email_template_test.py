import tempfile
import unittest
from pathlib import Path

from jinja2 import UndefinedError

from app.service.email_template import (
    TEMPLATES_DIR,
    EmailTemplate,
    EmailTemplateRenderer,
)

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

    def test_no_template_offers_snoozing_or_turning_off_reminders(self):
        for template in EmailTemplate:
            with self.subTest(template=template):
                html = self.renderer.render(template, CONTEXTS[template]).html.lower()

                self.assertNotIn("snooze", html)
                self.assertNotIn("turn off reminders", html)

    def test_footer_datasets_link_points_to_the_dataset_list(self):
        for template in EmailTemplate:
            if template in TRANSACTIONAL:
                continue
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


class TestPlainTextPart(unittest.TestCase):
    def setUp(self):
        self.renderer = EmailTemplateRenderer(site_url=SITE_URL)

    def test_a_template_without_a_text_file_gets_text_derived_from_its_html(self):
        email = self.renderer.render(
            EmailTemplate.NOTIFICATION, CONTEXTS[EmailTemplate.NOTIFICATION]
        )

        self.assertIn("André Maia approved your request.", email.text)
        self.assertIn(
            "Open dataset (https://datamap.example.org/datasets/7b21d4)", email.text
        )
        self.assertNotIn("<", email.text)
        self.assertNotIn("You now have access to Manaus", email.text)

    def test_a_text_file_beside_the_html_is_used_unescaped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notification.html").write_text(
                "{% block title %}{{ title }}{% endblock %}<p>{{ title }}</p>"
            )
            (root / "notification.txt").write_text(
                "Plain: {{ title }} at {{ site_url }}"
            )
            renderer = EmailTemplateRenderer(site_url=SITE_URL, templates_dir=root)

            email = renderer.render(EmailTemplate.NOTIFICATION, {"title": "A & B"})

        self.assertEqual(email.text, "Plain: A & B at https://datamap.example.org")
        self.assertIn("A &amp; B", email.html)

    def test_a_missing_variable_in_the_text_file_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notification.html").write_text("{% block title %}t{% endblock %}")
            (root / "notification.txt").write_text("{{ nowhere }}")
            renderer = EmailTemplateRenderer(site_url=SITE_URL, templates_dir=root)

            with self.assertRaises(UndefinedError):
                renderer.render(EmailTemplate.NOTIFICATION, {})

    def test_the_site_url_is_exposed_without_a_trailing_slash(self):
        self.assertEqual(self.renderer.site_url, "https://datamap.example.org")

    def test_the_subject_is_plain_text_not_html(self):
        context = {
            **CONTEXTS[EmailTemplate.NOTIFICATION],
            "title": "Ozone & CO2 — Ana's data",
        }

        email = self.renderer.render(EmailTemplate.NOTIFICATION, context)

        self.assertEqual(email.subject, "Ozone & CO2 — Ana's data")
        self.assertIn("Ozone &amp; CO2", email.html)


CONTEXTS[EmailTemplate.DATASET_INVITATION] = {
    "dataset_name": "GoAmazon 2014/5 — Aerosol size distribution, T3 site",
    "inviter_name": "Luciana Rizzo",
    "inviter_email": "luciana.rizzo@usp.br",
    "invited_address": "fernanda@inpe.br",
    "level": "read",
    "embargo_until_date": "December 15, 2026",
    "note": "Under review at JGR Atmospheres",
    "link": "https://datamap.example.org/invitations/tok",
}
CONTEXTS[EmailTemplate.EMBARGO_REMINDER] = {
    "dataset_name": "GoAmazon 2014/5 — Aerosol size distribution, T3 site",
    "is_owner": True,
    "can_extend": True,
    "days_remaining": 15,
    "embargo_until_date": "December 15, 2026",
    "embargo_until_short": "December 15",
    "tenancy_name": "Data Amazon",
    "members_can_edit": True,
    "owner_name": "Luciana Rizzo",
    "owner_email": "luciana.rizzo@usp.br",
    "people_with_access": ["You", "Alan Calheiros", "Caio Maia", "Fernanda Lima"],
    "anonymous_link_count": 2,
    "later_offsets": [10, 5, 1],
    "others_notified": True,
    "dataset_url": "https://datamap.example.org/app/datasets/1",
}
CONTEXTS[EmailTemplate.EMBARGO_ENDED] = {
    "dataset_name": "GoAmazon 2014/5 — Aerosol size distribution, T3 site",
    "is_owner": True,
    "ended_on_date": "December 15, 2026",
    "tenancy_name": "Data Amazon",
    "members_can_edit": True,
    "owner_name": "Luciana Rizzo",
    "owner_email": "luciana.rizzo@usp.br",
    "doi": "10.5281/datamap.3f9c1e",
    "doi_registered": True,
    "anonymous_link_count": 2,
    "dataset_url": "https://datamap.example.org/app/datasets/1",
}

TRANSACTIONAL = frozenset(
    {
        EmailTemplate.DATASET_INVITATION,
        EmailTemplate.EMBARGO_REMINDER,
        EmailTemplate.EMBARGO_ENDED,
    }
)
INVITATION = CONTEXTS[EmailTemplate.DATASET_INVITATION]
REMINDER = CONTEXTS[EmailTemplate.EMBARGO_REMINDER]
COLLABORATOR_REMINDER = {
    **REMINDER,
    "is_owner": False,
    "can_extend": False,
    "days_remaining": 5,
    "later_offsets": [1],
    "people_with_access": [],
    "anonymous_link_count": 0,
    "shared_by_name": "Luciana Rizzo",
}
ENDED = CONTEXTS[EmailTemplate.EMBARGO_ENDED]
COLLABORATOR_ENDED = {**ENDED, "is_owner": False, "shared_by_name": "Luciana Rizzo"}


class TestEmbargoTemplates(unittest.TestCase):
    def setUp(self):
        self.renderer = EmailTemplateRenderer(site_url=SITE_URL)

    def render(self, template, context):
        return self.renderer.render(template, context)

    def test_every_new_template_has_a_written_text_part(self):
        for template in TRANSACTIONAL:
            with self.subTest(template=template):
                self.assertTrue((TEMPLATES_DIR / f"{template.value}.txt").is_file())

    def test_no_new_template_offers_what_datamap_does_not_have(self):
        for template in TRANSACTIONAL:
            for suffix in (".html", ".txt"):
                body = (TEMPLATES_DIR / f"{template.value}{suffix}").read_text().lower()
                for word in ("unsubscribe", "preferences", "snooze"):
                    with self.subTest(template=template, suffix=suffix, word=word):
                        self.assertNotIn(word, body)

    def test_the_dataset_messages_carry_the_transactional_footer(self):
        for template in TRANSACTIONAL:
            with self.subTest(template=template):
                email = self.render(template, CONTEXTS[template])
                self.assertIn(
                    "This is a transactional message about a dataset you have access to",
                    email.html,
                )
                self.assertIn(
                    "This is a transactional message about a dataset you have access to",
                    email.text,
                )
                self.assertIn(
                    'href="https://datamap.example.org/project/support"', email.html
                )
                self.assertNotIn(">Data Policy</a>", email.html)

    def test_the_other_messages_keep_the_footer_links(self):
        email = self.render(
            EmailTemplate.NOTIFICATION, CONTEXTS[EmailTemplate.NOTIFICATION]
        )
        self.assertIn(">Data Policy</a>", email.html)
        self.assertNotIn("This is a transactional message", email.html)

    def test_the_dark_mode_block_styles_the_amber_note(self):
        base = (TEMPLATES_DIR / "base.html").read_text()
        self.assertIn(
            ".dm-amber{background-color:#3a2a0a!important;color:#fcd34d!important;}",
            base,
        )

    def test_the_invitation_follows_the_design(self):
        email = self.render(EmailTemplate.DATASET_INVITATION, INVITATION)

        self.assertEqual(email.subject, "Luciana Rizzo shared a dataset with you")
        self.assertIn(
            "It is under embargo: until it ends, only the owner and the people they share it with can see its files.",
            email.html,
        )
        self.assertIn("Note from Luciana", email.html)
        self.assertIn("Read and download", email.html)
        self.assertIn("Open the dataset", email.html)
        self.assertIn("Sign in with any account &mdash; ORCID or GitHub.", email.html)
        self.assertNotIn("Google", email.html)
        self.assertIn("Your access stays after the embargo ends.", email.html)
        self.assertIn(
            "because luciana.rizzo@usp.br invited fernanda@inpe.br to a dataset on DataMap",
            email.html,
        )
        self.assertIn("https://datamap.example.org/invitations/tok", email.html)
        self.assertIn("https://datamap.example.org/invitations/tok", email.text)

    def test_an_invitation_without_an_embargo_says_nothing_about_one(self):
        email = self.render(
            EmailTemplate.DATASET_INVITATION,
            {**INVITATION, "embargo_until_date": None, "note": None, "level": "write"},
        )

        self.assertNotIn("embargo", email.html.lower())
        self.assertNotIn("embargo", email.text.lower())
        self.assertIn("Read, download and edit", email.html)

    def test_the_owner_reminder_follows_the_design(self):
        email = self.render(EmailTemplate.EMBARGO_REMINDER, REMINDER)

        self.assertEqual(email.subject, "The embargo on your dataset ends in 15 days")
        self.assertIn("Your embargo ends in 15 days", email.html)
        self.assertIn("You, Alan Calheiros, Caio Maia, Fernanda Lima", email.html)
        self.assertIn("2 · keep working until you publish", email.html)
        self.assertIn("Review the embargo", email.html)
        self.assertIn(
            "You'll hear from us again 10, 5 and 1 day before it ends. The other people with access get the same reminders.",
            email.text,
        )
        self.assertIn(
            "You received this email because you own this dataset.", email.html
        )

    def test_the_last_owner_reminder_says_it_is_the_last(self):
        email = self.render(
            EmailTemplate.EMBARGO_REMINDER,
            {
                **REMINDER,
                "days_remaining": 1,
                "later_offsets": [],
                "others_notified": False,
            },
        )

        self.assertEqual(email.subject, "The embargo on your dataset ends in 1 day")
        self.assertIn("This is the last reminder.", email.text)
        self.assertNotIn("same reminders", email.text)

    def test_the_collaborator_reminder_names_the_owner_as_who_can_extend(self):
        email = self.render(EmailTemplate.EMBARGO_REMINDER, COLLABORATOR_REMINDER)

        self.assertEqual(
            email.subject, "The embargo on a dataset you have access to ends in 5 days"
        )
        self.assertIn("An embargo ends in 5 days", email.html)
        self.assertIn("Your own access doesn't change.", email.html)
        self.assertIn("Luciana Rizzo · luciana.rizzo@usp.br", email.html)
        self.assertIn("the owner, is the person who can do that", email.text)
        self.assertNotIn("Review the embargo", email.html)
        self.assertIn(
            "You received this email because Luciana Rizzo shared this dataset with you.",
            email.html,
        )

    def test_a_collaborator_who_can_extend_is_told_so(self):
        email = self.render(
            EmailTemplate.EMBARGO_REMINDER,
            {**COLLABORATOR_REMINDER, "can_extend": True, "owner_active": False},
        )

        self.assertIn("Review the embargo", email.html)
        self.assertIn(
            "The owner's account is no longer active, so anyone with access can extend it",
            email.text,
        )

    def test_the_owner_end_notice_explains_registered_but_not_findable(self):
        email = self.render(EmailTemplate.EMBARGO_ENDED, ENDED)

        self.assertEqual(
            email.subject, "The embargo on your dataset has ended — one step left"
        )
        self.assertIn("registered but not findable", email.html)
        self.assertIn("10.5281/datamap.3f9c1e · registered, not findable", email.html)
        self.assertIn("Nothing will do this for you.", email.text)
        self.assertIn("Make the DOI findable", email.html)
        self.assertIn('class="dm-amber"', email.html)
        self.assertNotIn("under review", email.html)
        self.assertIn(
            "Anonymous links keep showing the anonymised page until you publish",
            email.text,
        )

    def test_an_owner_without_a_registered_doi_is_told_to_create_one(self):
        email = self.render(
            EmailTemplate.EMBARGO_ENDED, {**ENDED, "doi": None, "doi_registered": False}
        )

        self.assertIn(
            "create a DOI from the dataset page and make it findable", email.text
        )
        self.assertNotIn("registered but not findable", email.text)

    def test_an_early_end_says_who_ended_it(self):
        owner = self.render(EmailTemplate.EMBARGO_ENDED, {**ENDED, "ended_early": True})
        other = self.render(
            EmailTemplate.EMBARGO_ENDED, {**COLLABORATOR_ENDED, "ended_early": True}
        )

        self.assertIn(
            "You ended the embargo on the dataset below early, today,", owner.text
        )
        self.assertIn(
            "Luciana Rizzo ended the embargo on the dataset below early, today,",
            other.text,
        )

    def test_the_collaborator_end_notice_does_not_guess_a_pronoun(self):
        email = self.render(EmailTemplate.EMBARGO_ENDED, COLLABORATOR_ENDED)

        self.assertEqual(
            email.subject, "The embargo on a dataset you have access to has ended"
        )
        self.assertIn("this may be a good moment to check with them", email.text)
        self.assertNotIn(" her.", email.text)
        self.assertNotIn(" him.", email.text)

    def test_an_end_by_manual_doi_says_why_and_that_the_page_is_public(self):
        email = self.render(
            EmailTemplate.EMBARGO_ENDED,
            {
                **ENDED,
                "doi": "10.1029/2026JD041877",
                "ended_early": True,
                "ended_by_manual_doi": True,
            },
        )

        self.assertIn(
            "Registering the external DOI 10.1029/2026JD041877 ended the embargo",
            email.text,
        )
        self.assertIn("Published, with the authors", email.html)
        self.assertNotIn("Nothing has been made public", email.text)
        self.assertNotIn("Make the DOI findable", email.html)

    def test_dataset_names_are_escaped_in_html_and_plain_in_the_subject(self):
        email = self.render(
            EmailTemplate.EMBARGO_ENDED,
            {**COLLABORATOR_ENDED, "dataset_name": "<b>O3 & CO</b>"},
        )

        self.assertIn("&lt;b&gt;O3 &amp; CO&lt;/b&gt;", email.html)
        self.assertIn("<b>O3 & CO</b>", email.text)

    def test_a_missing_owner_name_fails_here_not_in_an_inbox(self):
        context = {
            key: value
            for key, value in COLLABORATOR_REMINDER.items()
            if key != "owner_name"
        }

        with self.assertRaises(UndefinedError):
            self.render(EmailTemplate.EMBARGO_REMINDER, context)


class TestMembersSentence(unittest.TestCase):
    def setUp(self):
        self.renderer = EmailTemplateRenderer(site_url=SITE_URL)

    def render(self, template, context):
        return self.renderer.render(template, context)

    def assert_in_both(self, sentence, email):
        self.assertIn(sentence, email.html)
        self.assertIn(sentence, email.text)

    def test_the_owner_reminder_says_members_can_edit_again(self):
        email = self.render(EmailTemplate.EMBARGO_REMINDER, REMINDER)

        self.assert_in_both(
            "When the embargo ends, members of Data Amazon can read and edit this dataset again; "
            "the people you shared it with keep their access.",
            email,
        )

    def test_the_owner_reminder_says_editing_stays_with_the_people_shared_with(self):
        email = self.render(
            EmailTemplate.EMBARGO_REMINDER, {**REMINDER, "members_can_edit": False}
        )

        self.assert_in_both(
            "When the embargo ends, members of Data Amazon can read this dataset; "
            "editing stays with the people you shared it with.",
            email,
        )
        self.assertNotIn("can read and edit", email.text)

    def test_the_collaborator_reminder_names_the_owner(self):
        editable = self.render(EmailTemplate.EMBARGO_REMINDER, COLLABORATOR_REMINDER)
        read_only = self.render(
            EmailTemplate.EMBARGO_REMINDER,
            {**COLLABORATOR_REMINDER, "members_can_edit": False},
        )

        self.assert_in_both(
            "When the embargo ends, members of Data Amazon can read and edit this dataset again; "
            "the people Luciana Rizzo shared it with keep their access.",
            editable,
        )
        self.assert_in_both(
            "When the embargo ends, members of Data Amazon can read this dataset; "
            "editing stays with Luciana Rizzo and the people they shared it with.",
            read_only,
        )

    def test_the_owner_end_notice_says_what_members_got_back(self):
        editable = self.render(EmailTemplate.EMBARGO_ENDED, ENDED)
        read_only = self.render(
            EmailTemplate.EMBARGO_ENDED, {**ENDED, "members_can_edit": False}
        )

        self.assert_in_both(
            "Members of Data Amazon can read and edit this dataset again; "
            "the people you shared it with keep their access.",
            editable,
        )
        self.assert_in_both(
            "Members of Data Amazon can read this dataset; "
            "editing stays with the people you shared it with.",
            read_only,
        )

    def test_the_collaborator_end_notice_names_the_owner(self):
        editable = self.render(EmailTemplate.EMBARGO_ENDED, COLLABORATOR_ENDED)
        read_only = self.render(
            EmailTemplate.EMBARGO_ENDED,
            {**COLLABORATOR_ENDED, "members_can_edit": False},
        )

        self.assert_in_both(
            "Members of Data Amazon can read and edit this dataset again; "
            "the people Luciana Rizzo shared it with keep their access.",
            editable,
        )
        self.assert_in_both(
            "Members of Data Amazon can read this dataset; "
            "editing stays with Luciana Rizzo and the people they shared it with.",
            read_only,
        )

    def test_an_end_by_manual_doi_says_it_too(self):
        email = self.render(
            EmailTemplate.EMBARGO_ENDED,
            {
                **ENDED,
                "doi": "10.1029/2026JD041877",
                "ended_early": True,
                "ended_by_manual_doi": True,
            },
        )

        self.assert_in_both(
            "Members of Data Amazon can read and edit this dataset again; "
            "the people you shared it with keep their access.",
            email,
        )

    def test_the_sentence_is_a_paragraph_of_its_own_in_the_text(self):
        reminder = self.render(EmailTemplate.EMBARGO_REMINDER, REMINDER).text
        ended = self.render(EmailTemplate.EMBARGO_ENDED, COLLABORATOR_ENDED).text

        self.assertIn("\n\nWhen the embargo ends, members of Data Amazon", reminder)
        self.assertIn("keep their access.\n\n", reminder)
        self.assertIn("\n\nMembers of Data Amazon can read and edit", ended)

    def test_a_context_without_the_setting_fails_here_not_in_an_inbox(self):
        for template, context in (
            (EmailTemplate.EMBARGO_REMINDER, REMINDER),
            (EmailTemplate.EMBARGO_ENDED, ENDED),
        ):
            with self.subTest(template=template):
                partial = {
                    key: value
                    for key, value in context.items()
                    if key != "members_can_edit"
                }
                with self.assertRaises(UndefinedError):
                    self.render(template, partial)


CONTEXTS[EmailTemplate.SIGN_UP_CODE] = {
    "name": "Ana Souza",
    "code": "042917",
    "expires_in_minutes": 15,
}
CONTEXTS[EmailTemplate.EMAIL_VERIFICATION_CODE] = {
    "name": "Ana Souza",
    "code": "042917",
    "orcid": "0000-0002-1825-0097",
    "expires_in_minutes": 15,
}
CONTEXTS[EmailTemplate.PASSWORD_RESET] = {
    "name": "Ana Souza",
    "link": "https://datamap.example.org/account/reset-password/tok-123",
}
CONTEXTS[EmailTemplate.SIGN_UP_EXISTING_ACCOUNT] = {
    "name": "Ana Souza",
    "link": "https://datamap.example.org/account/reset-password/tok-123",
}
CONTEXTS[EmailTemplate.NEW_ACCOUNT_PENDING] = {
    "name": "Ana Souza",
    "email": "ana.souza@usp.br",
    "sign_in_method": "Email and password",
    "created_at": "October 3, 2026 at 14:05 UTC",
}

ACCOUNT = frozenset(
    {
        EmailTemplate.SIGN_UP_CODE,
        EmailTemplate.EMAIL_VERIFICATION_CODE,
        EmailTemplate.PASSWORD_RESET,
        EmailTemplate.SIGN_UP_EXISTING_ACCOUNT,
        EmailTemplate.NEW_ACCOUNT_PENDING,
    }
)


class TestAccountTemplates(unittest.TestCase):
    def setUp(self):
        self.renderer = EmailTemplateRenderer(site_url=SITE_URL)

    def render(self, template):
        return self.renderer.render(template, CONTEXTS[template])

    def test_every_account_template_has_a_written_text_part(self):
        for template in ACCOUNT:
            with self.subTest(template=template):
                self.assertTrue((TEMPLATES_DIR / f"{template.value}.txt").is_file())

    def test_a_code_is_in_both_bodies_and_never_in_the_subject(self):
        for template in (
            EmailTemplate.SIGN_UP_CODE,
            EmailTemplate.EMAIL_VERIFICATION_CODE,
        ):
            with self.subTest(template=template):
                email = self.render(template)

                self.assertIn("042917", email.html)
                self.assertIn("Your DataMap code: 042917", email.text)
                self.assertNotIn("042917", email.subject)

    def test_the_sign_up_code_tells_a_stranger_to_ignore_it(self):
        email = self.render(EmailTemplate.SIGN_UP_CODE)

        self.assertEqual(email.subject, "Confirm your email for DataMap")
        self.assertIn("If this wasn't you, ignore this email.", email.text)
        self.assertIn("It expires in 15 minutes.", email.text)

    def test_the_email_verification_names_the_orcid_being_linked(self):
        email = self.render(EmailTemplate.EMAIL_VERIFICATION_CODE)

        self.assertEqual(email.subject, "Confirm your email to sign in with ORCID")
        self.assertIn("0000-0002-1825-0097", email.html)
        self.assertIn("ORCID iD: 0000-0002-1825-0097", email.text)

    def test_the_reset_link_is_in_both_bodies_and_valid_for_an_hour(self):
        email = self.render(EmailTemplate.PASSWORD_RESET)
        link = "https://datamap.example.org/account/reset-password/tok-123"

        self.assertEqual(email.subject, "Reset your DataMap password")
        self.assertIn(link, email.html)
        self.assertIn(link, email.text)
        self.assertNotIn("tok-123", email.subject)
        self.assertIn("valid for 1 hour", email.text)

    def test_a_sign_up_for_an_existing_account_offers_a_reset_instead(self):
        email = self.render(EmailTemplate.SIGN_UP_EXISTING_ACCOUNT)
        link = "https://datamap.example.org/account/reset-password/tok-123"

        self.assertEqual(email.subject, "You already have a DataMap account")
        self.assertIn(link, email.html)
        self.assertIn(link, email.text)
        self.assertNotIn("tok-123", email.subject)
        for sentence in (
            "You already have a DataMap account with this address.",
            "If you forgot your password, reset it with this link, valid for 1 hour.",
            "If you did not try to create an account, ignore this email.",
        ):
            with self.subTest(sentence=sentence):
                self.assertIn(sentence, email.text)
                self.assertIn(sentence, email.html)

    def test_the_admin_notification_lists_the_account(self):
        email = self.render(EmailTemplate.NEW_ACCOUNT_PENDING)

        self.assertEqual(email.subject, "New DataMap account: Ana Souza")
        for value in (
            "Ana Souza",
            "ana.souza@usp.br",
            "Email and password",
            "October 3, 2026 at 14:05 UTC",
        ):
            with self.subTest(value=value):
                self.assertIn(value, email.text)
                self.assertIn(value, email.html)

    def test_account_messages_do_not_claim_to_be_about_a_dataset(self):
        for template in ACCOUNT:
            with self.subTest(template=template):
                email = self.render(template)
                self.assertNotIn("transactional message about a dataset", email.html)
                self.assertNotIn("transactional message about a dataset", email.text)

    def test_a_name_is_escaped_in_html(self):
        email = self.renderer.render(
            EmailTemplate.SIGN_UP_CODE,
            {**CONTEXTS[EmailTemplate.SIGN_UP_CODE], "name": "<b>Ana</b>"},
        )

        self.assertNotIn("<b>Ana</b>", email.html)
        self.assertIn("&lt;b&gt;Ana&lt;/b&gt;", email.html)

    def test_a_name_is_escaped_in_the_existing_account_html(self):
        email = self.renderer.render(
            EmailTemplate.SIGN_UP_EXISTING_ACCOUNT,
            {**CONTEXTS[EmailTemplate.SIGN_UP_EXISTING_ACCOUNT], "name": "<b>Ana</b>"},
        )

        self.assertNotIn("<b>Ana</b>", email.html)
        self.assertIn("&lt;b&gt;Ana&lt;/b&gt;", email.html)
