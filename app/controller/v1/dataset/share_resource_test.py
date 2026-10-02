import unittest
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from app.controller.v1.dataset.share_resource import (
    CreateAnonymousLinkBody,
    adapt_grant_result,
    adapt_anonymous_page,
)
from app.model.sharing import (
    GrantResult,
    InvitationView,
    AnonymousPage,
    AnonymousVersion,
)

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class TestAdapters(unittest.TestCase):
    def test_an_invitation_result_carries_its_link(self):
        invitation = InvitationView(
            id=uuid4(),
            email="dora@ufam.edu.br",
            orcid=None,
            level="read",
            created_at=NOW,
        )
        body = adapt_grant_result(
            GrantResult(
                kind="invitation", invitation=invitation, link="https://x/invitations/t"
            )
        ).model_dump(mode="json", exclude_none=True)

        self.assertEqual(body["kind"], "invitation")
        self.assertEqual(body["link"], "https://x/invitations/t")
        self.assertEqual(body["invitation"]["email"], "dora@ufam.edu.br")
        self.assertNotIn("permission", body)

    def test_an_active_anonymous_page_has_versions_with_file_summaries(self):
        page = AnonymousPage(
            state="active",
            dataset_id=uuid4(),
            embargo_until=NOW,
            name="Ozone",
            data={"authors": [{"name": "[redacted]"}]},
            versions=[
                AnonymousVersion(
                    name="1", created_at=NOW, file_count=2, total_size_bytes=42
                )
            ],
        )
        body = adapt_anonymous_page(page)

        self.assertEqual(body["state"], "active")
        self.assertEqual(body["dataset"]["name"], "Ozone")
        self.assertEqual(
            body["dataset"]["versions"][0]["files_summary"],
            {"count": 2, "total_size_bytes": 42},
        )
        self.assertNotIn("dataset_id", body)

    def test_an_ended_anonymous_page_keeps_the_redacted_dataset(self):
        page = AnonymousPage(
            state="ended",
            dataset_id=uuid4(),
            embargo_ended_at=NOW,
            name="Ozone",
            data={"authors": [{"name": "[redacted]"}]},
            versions=[
                AnonymousVersion(
                    name="1", created_at=NOW, file_count=2, total_size_bytes=42
                )
            ],
        )
        body = adapt_anonymous_page(page)

        self.assertEqual(body["state"], "ended")
        self.assertEqual(body["embargo_ended_at"], NOW.isoformat())
        self.assertEqual(body["dataset"]["data"], {"authors": [{"name": "[redacted]"}]})
        self.assertNotIn("dataset_id", body)

    def test_a_published_anonymous_page_says_only_where_to_go(self):
        dataset_id = uuid4()
        body = adapt_anonymous_page(
            AnonymousPage(state="published", dataset_id=dataset_id)
        )
        self.assertEqual(body, {"state": "published", "dataset_id": str(dataset_id)})


class TestCreateAnonymousLinkBody(unittest.TestCase):
    def test_the_label_is_stripped(self):
        self.assertEqual(
            CreateAnonymousLinkBody(label="  JGR round 1 ").label, "JGR round 1"
        )

    def test_a_whitespace_only_label_is_rejected(self):
        with self.assertRaises(ValidationError):
            CreateAnonymousLinkBody(label="   ")

    def test_a_label_of_256_characters_after_stripping_is_accepted(self):
        self.assertEqual(
            len(CreateAnonymousLinkBody(label=" " + "a" * 256 + " ").label), 256
        )

    def test_a_label_longer_than_256_characters_is_rejected(self):
        with self.assertRaises(ValidationError):
            CreateAnonymousLinkBody(label="a" * 257)
