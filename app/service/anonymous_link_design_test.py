import unittest
from types import SimpleNamespace
from uuid import uuid4

from app.controller.v1.dataset.share_resource import (
    adapt_anonymous_link,
    adapt_anonymous_page,
)
from app.model.sharing import (
    AnonymousExtension,
    AnonymousLinkView,
    AnonymousPage,
    AnonymousVersion,
)
from app.service.anonymous_link_test import NOW, AnonymousLinkTestCase
from app.service.share_token import token_hint


class TestTokenHint(unittest.TestCase):
    def test_the_hint_keeps_four_characters_at_each_end(self):
        self.assertEqual(
            token_hint("9f2cAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAa71e"), "9f2c…a71e"
        )


class TestCreateKeepsTheHint(AnonymousLinkTestCase):
    def test_the_hint_is_stored_and_returned_and_matches_the_link(self):
        self.links.create.side_effect = lambda link: SimpleNamespace(
            id=uuid4(),
            label=link.label,
            created_at=NOW,
            revoked_at=None,
            token_hash=link.token_hash,
            token_hint=link.token_hint,
        )

        view, link = self.service.create(self.dataset.id, uuid4(), "JGR, round 2")

        token = link.rsplit("/", 1)[1]
        self.assertEqual(
            self.links.create.call_args.args[0].token_hint, token_hint(token)
        )
        self.assertEqual(view.token_hint, token_hint(token))


class TestThePageGroupsFilesByType(AnonymousLinkTestCase):
    def test_extensions_are_counted_and_sized_largest_first(self):
        self.dataset.versions[0].files_in = [
            SimpleNamespace(size_bytes=100, extension=".nc"),
            SimpleNamespace(size_bytes=300, extension=".nc"),
            SimpleNamespace(size_bytes=50, extension=".csv"),
            SimpleNamespace(size_bytes=7, extension=None),
        ]
        self.links.fetch_by_token_hash.return_value = SimpleNamespace(
            id=uuid4(), dataset_id=self.dataset.id, revoked_at=None
        )

        page = self.service.view("tok")

        self.assertEqual(
            page.versions[0].extensions,
            [
                AnonymousExtension(extension=".nc", count=2, total_size_bytes=400),
                AnonymousExtension(extension=".csv", count=1, total_size_bytes=50),
                AnonymousExtension(extension=None, count=1, total_size_bytes=7),
            ],
        )


class TestAdapters(unittest.TestCase):
    def test_the_link_response_carries_the_hint(self):
        response = adapt_anonymous_link(
            AnonymousLinkView(
                id=uuid4(), label="JGR", created_at=NOW, token_hint="9f2c…a71e"
            )
        )
        self.assertEqual(response.token_hint, "9f2c…a71e")

    def test_the_page_lists_extensions_in_the_files_summary(self):
        page = AnonymousPage(
            state="active",
            dataset_id=uuid4(),
            embargo_until=NOW,
            name="Ozone",
            versions=[
                AnonymousVersion(
                    name="1",
                    created_at=NOW,
                    file_count=1,
                    total_size_bytes=5,
                    extensions=[
                        AnonymousExtension(extension=".nc", count=1, total_size_bytes=5)
                    ],
                )
            ],
        )

        summary = adapt_anonymous_page(page)["dataset"]["versions"][0]["files_summary"]

        self.assertEqual(
            summary["extensions"],
            [{"extension": ".nc", "count": 1, "total_size_bytes": 5}],
        )
