import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from prometheus_client import REGISTRY

from app.exception.bad_request import BadRequestException
from app.exception.not_found import NotFoundException
from app.model.dataset import VisibilityStatus
from app.model.dataset_access import AccessEventType, AccessLevel, DatasetAction
from app.repository.dataset import DatasetRepository
from app.repository.dataset_anonymous_link import DatasetAnonymousLinkRepository
from app.service.dataset import DatasetService
from app.service.dataset_access_audit import DatasetAccessAudit
from app.service.anonymous_link import AnonymousLinkService
from app.service.share_token import hash_token

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
TENANCY = "datamap/production/data-amazon"


def _sample(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0.0


def dataset(until=NOW + timedelta(days=30), visibility=VisibilityStatus.PRIVATE):
    files = [SimpleNamespace(size_bytes=10), SimpleNamespace(size_bytes=32)]
    return SimpleNamespace(
        id=uuid4(),
        name="Ozone at ATTO",
        tenancy=TENANCY,
        embargo_until=until,
        visibility=visibility,
        data={"description": "Ozone", "authors": [{"name": "Ana"}]},
        versions=[
            SimpleNamespace(name="1", created_at=NOW, is_enabled=True, files_in=files),
            SimpleNamespace(name="0", created_at=NOW, is_enabled=False, files_in=[]),
        ],
    )


class AnonymousLinkTestCase(unittest.TestCase):
    def setUp(self):
        self.dataset_service = Mock(spec=DatasetService)
        self.links = Mock(spec=DatasetAnonymousLinkRepository)
        self.datasets = Mock(spec=DatasetRepository)
        self.audit = Mock(spec=DatasetAccessAudit)
        self.dataset = dataset()
        self.dataset_service.fetch_authorized.return_value = (
            self.dataset,
            [],
            AccessLevel.OWNER,
        )
        self.datasets.fetch.return_value = self.dataset
        self.links.create.side_effect = lambda link: SimpleNamespace(
            id=uuid4(),
            label=link.label,
            created_at=NOW,
            revoked_at=None,
            token_hash=link.token_hash,
        )
        self.service = AnonymousLinkService(
            dataset_service=self.dataset_service,
            anonymous_link_repository=self.links,
            dataset_repository=self.datasets,
            audit=self.audit,
            public_base_url="https://datamap.pcs.usp.br/",
            clock=lambda: NOW,
        )


class TestCreate(AnonymousLinkTestCase):
    def test_a_link_is_created_while_the_embargo_lasts(self):
        before = _sample("datamap_anonymous_links_created_total", tenancy=TENANCY)

        view, link = self.service.create(self.dataset.id, uuid4(), "JGR, round 1")

        self.assertEqual(
            self.dataset_service.fetch_authorized.call_args.kwargs["action"],
            DatasetAction.WRITE,
        )
        self.assertTrue(link.startswith("https://datamap.pcs.usp.br/anonymous/"))
        token = link.rsplit("/", 1)[1]
        self.assertEqual(
            self.links.create.call_args.args[0].token_hash, hash_token(token)
        )
        self.assertEqual(view.label, "JGR, round 1")
        self.assertEqual(
            self.audit.record.call_args.kwargs["event_type"],
            AccessEventType.ANONYMOUS_LINK_CREATED,
        )
        self.assertEqual(
            _sample("datamap_anonymous_links_created_total", tenancy=TENANCY) - before,
            1.0,
        )

    def test_no_link_without_an_active_embargo(self):
        self.dataset_service.fetch_authorized.return_value = (
            dataset(until=NOW - timedelta(seconds=1)),
            [],
            AccessLevel.OWNER,
        )
        with self.assertRaises(BadRequestException) as caught:
            self.service.create(self.dataset.id, uuid4(), "JGR")
        self.assertEqual(caught.exception.errors[0].code, "embargo_not_active")


class TestView(AnonymousLinkTestCase):
    def setUp(self):
        super().setUp()
        self.link = SimpleNamespace(
            id=uuid4(), dataset_id=self.dataset.id, revoked_at=None
        )
        self.links.fetch_by_token_hash.return_value = self.link

    def test_an_active_embargo_shows_redacted_metadata_and_counts_only(self):
        before = _sample(
            "datamap_anonymous_link_views_total", tenancy=TENANCY, outcome="shown"
        )

        page = self.service.view("tok")

        self.links.fetch_by_token_hash.assert_called_once_with(hash_token("tok"))
        self.assertEqual(page.state, "active")
        self.assertEqual(page.data["authors"], [{"name": "[redacted]"}])
        self.assertEqual(page.data["description"], "Ozone")
        self.assertEqual(len(page.versions), 1)
        self.assertEqual(page.versions[0].file_count, 2)
        self.assertEqual(page.versions[0].total_size_bytes, 42)
        self.links.record_view.assert_called_once_with(self.link.id, "shown")
        self.assertEqual(
            _sample(
                "datamap_anonymous_link_views_total", tenancy=TENANCY, outcome="shown"
            )
            - before,
            1.0,
        )

    def test_after_the_embargo_an_unpublished_dataset_stays_anonymised(self):
        ended_at = NOW - timedelta(days=1)
        self.datasets.fetch.return_value = dataset(until=ended_at)
        before = _sample(
            "datamap_anonymous_link_views_total",
            tenancy=TENANCY,
            outcome="shown_after_embargo",
        )

        page = self.service.view("tok")

        self.assertEqual(page.state, "ended")
        self.assertEqual(page.embargo_ended_at, ended_at)
        self.assertEqual(page.data["authors"], [{"name": "[redacted]"}])
        self.assertEqual(page.versions[0].file_count, 2)
        self.links.record_view.assert_called_once_with(
            self.link.id, "shown_after_embargo"
        )
        self.assertEqual(
            _sample(
                "datamap_anonymous_link_views_total",
                tenancy=TENANCY,
                outcome="shown_after_embargo",
            )
            - before,
            1.0,
        )

    def test_once_published_the_link_points_to_the_public_page(self):
        published = dataset(
            until=NOW - timedelta(days=1), visibility=VisibilityStatus.PUBLIC
        )
        self.datasets.fetch.return_value = published

        page = self.service.view("tok")

        self.assertEqual(page.state, "published")
        self.assertEqual(page.dataset_id, published.id)
        self.assertEqual(page.data, {})
        self.links.record_view.assert_called_once_with(self.link.id, "redirected")

    def test_a_revoked_link_is_not_found(self):
        self.link.revoked_at = NOW
        before = _sample(
            "datamap_anonymous_link_views_total", tenancy="none", outcome="not_found"
        )
        with self.assertRaises(NotFoundException):
            self.service.view("tok")
        self.links.record_view.assert_not_called()
        self.assertEqual(
            _sample(
                "datamap_anonymous_link_views_total",
                tenancy="none",
                outcome="not_found",
            )
            - before,
            1.0,
        )

    def test_an_unknown_token_is_not_found(self):
        self.links.fetch_by_token_hash.return_value = None
        with self.assertRaises(NotFoundException):
            self.service.view("tok")


class TestRevoke(AnonymousLinkTestCase):
    def test_revoking_records_the_event(self):
        link_id = uuid4()
        self.links.fetch.return_value = SimpleNamespace(id=link_id, revoked_at=None)

        self.service.revoke(self.dataset.id, uuid4(), link_id)

        self.links.revoke.assert_called_once_with(link_id, NOW)
        self.assertEqual(
            self.audit.record.call_args.kwargs["event_type"],
            AccessEventType.ANONYMOUS_LINK_REVOKED,
        )

    def test_revoking_an_unknown_link_is_not_found(self):
        self.links.fetch.return_value = None
        with self.assertRaises(NotFoundException):
            self.service.revoke(self.dataset.id, uuid4(), uuid4())

    def test_a_link_revoked_meanwhile_is_not_found_and_not_audited(self):
        link_id = uuid4()
        self.links.fetch.return_value = SimpleNamespace(id=link_id, revoked_at=None)
        self.links.revoke.return_value = False

        with self.assertRaises(NotFoundException):
            self.service.revoke(self.dataset.id, uuid4(), link_id)
        self.audit.record.assert_not_called()
