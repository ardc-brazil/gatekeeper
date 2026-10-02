import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.exception.bad_request import BadRequestException
from app.exception.not_found import NotFoundException
from app.model.dataset_access import (
    AccessEventType,
    AccessLevel,
    DatasetAction,
    PermissionLevel,
)
from app.model.sharing import GrantRequest
from app.repository.dataset import DatasetRepository
from app.repository.dataset_invitation import DatasetInvitationRepository
from app.repository.dataset_anonymous_link import DatasetAnonymousLinkRepository
from app.repository.permission import PermissionRepository
from app.repository.user import UserRepository
from app.service.dataset import DatasetService
from app.service.email import EmailService
from app.service.dataset_access_audit import DatasetAccessAudit
from app.service.permission import PermissionService
from app.service.share import ShareService
from app.service.share_token import hash_token
from app.service.user import UserService

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
OWNER = uuid4()
CALLER = uuid4()


def user_row(user_id=None, name="Ana", email="ana@usp.br"):
    return SimpleNamespace(id=user_id or uuid4(), name=name, email=email, providers=[])


class ShareServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.datasets = Mock(spec=DatasetService)
        self.dataset_repository = Mock(spec=DatasetRepository)
        self.permissions = Mock(spec=PermissionRepository)
        self.permission_service = Mock(spec=PermissionService)
        self.invitations = Mock(spec=DatasetInvitationRepository)
        self.anonymous_links = Mock(spec=DatasetAnonymousLinkRepository)
        self.users = Mock(spec=UserRepository)
        self.user_service = Mock(spec=UserService)
        self.audit = Mock(spec=DatasetAccessAudit)
        self.email = Mock(spec=EmailService)
        self.dataset = SimpleNamespace(
            id=uuid4(),
            name="Ozone at ATTO",
            owner_id=OWNER,
            tenancy="datamap/production/data-amazon",
            embargo_until=NOW + timedelta(days=30),
            embargo_note="Under review at JGR Atmospheres",
        )
        self.datasets.fetch_authorized.return_value = (
            self.dataset,
            [],
            AccessLevel.OWNER,
        )
        self.dataset_repository.fetch.return_value = self.dataset
        self.permissions.fetch.return_value = None
        self.permissions.list_for_dataset.return_value = []
        self.permission_service.grant.side_effect = (
            lambda dataset_id, user_id, level, granted_by: SimpleNamespace(
                user_id=user_id, level=level, created_at=NOW, granted_by=granted_by
            )
        )
        self.permission_service.revoke.return_value = False
        self.invitations.find_pending.return_value = None
        self.users.fetch_by_id.side_effect = lambda id, is_enabled=True: user_row(
            id, name="Caller"
        )
        self.service = ShareService(
            dataset_service=self.datasets,
            dataset_repository=self.dataset_repository,
            permission_repository=self.permissions,
            permission_service=self.permission_service,
            invitation_repository=self.invitations,
            anonymous_link_repository=self.anonymous_links,
            user_repository=self.users,
            user_service=self.user_service,
            audit=self.audit,
            email_service=self.email,
            public_base_url="https://datamap.pcs.usp.br",
            clock=lambda: NOW,
        )


class TestGrantTargets(ShareServiceTestCase):
    def test_no_target_is_refused(self):
        with self.assertRaises(BadRequestException) as caught:
            self.service.grant(self.dataset.id, CALLER, GrantRequest(level="read"))
        self.assertEqual(caught.exception.errors[0].code, "share_target_required")

    def test_two_targets_are_refused(self):
        with self.assertRaises(BadRequestException) as caught:
            self.service.grant(
                self.dataset.id,
                CALLER,
                GrantRequest(level="read", email="a@b.co", orcid="0000-0002-1825-0097"),
            )
        self.assertEqual(caught.exception.errors[0].code, "share_target_ambiguous")

    def test_an_unknown_level_is_refused(self):
        with self.assertRaises(BadRequestException) as caught:
            self.service.grant(
                self.dataset.id, CALLER, GrantRequest(level="admin", email="a@b.co")
            )
        self.assertEqual(caught.exception.errors[0].code, "invalid_level")

    def test_the_caller_needs_write_access(self):
        self.datasets.fetch_authorized.side_effect = NotFoundException("not_found")
        with self.assertRaises(NotFoundException):
            self.service.grant(
                self.dataset.id, CALLER, GrantRequest(level="read", email="a@b.co")
            )
        self.datasets.fetch_authorized.assert_called_once_with(
            dataset_id=self.dataset.id,
            user_id=CALLER,
            tenancies=None,
            action=DatasetAction.WRITE,
        )


class TestGrantToAnExistingAccount(ShareServiceTestCase):
    def test_an_email_that_matches_an_account_grants_now(self):
        target = user_row(name="Bruno", email="bruno@inpa.gov.br")
        self.users.fetch_by_email_insensitive.return_value = target

        result = self.service.grant(
            self.dataset.id,
            CALLER,
            GrantRequest(level="read", email="Bruno@INPA.gov.br"),
        )

        self.assertEqual(result.kind, "permission")
        self.assertEqual(result.permission.level, "read")
        self.users.fetch_by_email_insensitive.assert_called_once_with(
            "bruno@inpa.gov.br"
        )
        self.permission_service.grant.assert_called_once_with(
            self.dataset.id, target.id, PermissionLevel.READ, CALLER
        )
        self.assertEqual(
            self.email.enqueue.call_args.kwargs["template"], "notification"
        )
        self.assertEqual(
            self.email.enqueue.call_args.kwargs["context"]["cta_url"].rsplit("/", 2)[
                -2
            ],
            "datasets",
        )
        self.assertEqual(
            self.email.enqueue.call_args.kwargs["recipient"], "bruno@inpa.gov.br"
        )

    def test_an_orcid_is_matched_through_the_orcid_provider(self):
        target = user_row(name="Carla", email=None)
        self.users.fetch_by_provider.return_value = target

        self.service.grant(
            self.dataset.id,
            CALLER,
            GrantRequest(level="write", orcid="https://orcid.org/0000-0002-1825-0097"),
        )

        self.users.fetch_by_provider.assert_called_once_with(
            provider_name="orcid", reference="0000-0002-1825-0097"
        )
        self.email.enqueue.assert_not_called()

    def test_the_owner_cannot_be_granted(self):
        self.users.fetch_by_id.side_effect = None
        self.users.fetch_by_id.return_value = user_row(OWNER)
        with self.assertRaises(BadRequestException) as caught:
            self.service.grant(
                self.dataset.id, CALLER, GrantRequest(level="read", user_id=OWNER)
            )
        self.assertEqual(caught.exception.errors[0].code, "cannot_share_with_owner")

    def test_someone_who_already_has_access_is_refused(self):
        target = user_row()
        self.users.fetch_by_email_insensitive.return_value = target
        self.permissions.fetch.return_value = SimpleNamespace(level="read")
        with self.assertRaises(BadRequestException) as caught:
            self.service.grant(
                self.dataset.id, CALLER, GrantRequest(level="read", email=target.email)
            )
        self.assertEqual(caught.exception.errors[0].code, "already_has_access")

    def test_an_unknown_user_id_is_refused(self):
        self.users.fetch_by_id.side_effect = None
        self.users.fetch_by_id.return_value = None
        with self.assertRaises(BadRequestException) as caught:
            self.service.grant(
                self.dataset.id, CALLER, GrantRequest(level="read", user_id=uuid4())
            )
        self.assertEqual(caught.exception.errors[0].code, "unknown_user")

    def test_a_failure_to_queue_the_email_does_not_undo_the_grant(self):
        target = user_row()
        self.users.fetch_by_email_insensitive.return_value = target
        self.email.enqueue.side_effect = RuntimeError("database gone")

        result = self.service.grant(
            self.dataset.id, CALLER, GrantRequest(level="read", email=target.email)
        )

        self.assertEqual(result.kind, "permission")


class TestInvitation(ShareServiceTestCase):
    def setUp(self):
        super().setUp()
        self.users.fetch_by_email_insensitive.return_value = None
        self.users.fetch_by_provider.return_value = None
        self.invitations.create.side_effect = lambda invitation: SimpleNamespace(
            id=uuid4(),
            email=invitation.email,
            orcid=invitation.orcid,
            level=invitation.level,
            token_hash=invitation.token_hash,
            created_at=NOW,
            accepted_at=None,
            accepted_by=None,
            revoked_at=None,
        )

    def test_an_unknown_email_becomes_an_invitation_with_a_link_and_an_email(self):
        result = self.service.grant(
            self.dataset.id,
            CALLER,
            GrantRequest(level="read", email="dora@ufam.edu.br"),
        )

        self.assertEqual(result.kind, "invitation")
        self.assertTrue(
            result.link.startswith("https://datamap.pcs.usp.br/invitations/")
        )
        token = result.link.rsplit("/", 1)[1]
        stored = self.invitations.create.call_args.args[0]
        self.assertEqual(stored.token_hash, hash_token(token))
        enqueue = self.email.enqueue.call_args.kwargs
        self.assertEqual(enqueue["template"], "dataset_invitation")
        self.assertEqual(enqueue["recipient"], "dora@ufam.edu.br")
        self.assertEqual(enqueue["secret_fields"], frozenset({"link"}))
        self.assertEqual(enqueue["context"]["link"], result.link)
        self.assertEqual(enqueue["context"]["invited_address"], "dora@ufam.edu.br")
        self.assertEqual(enqueue["context"]["embargo_until_date"], "October 31, 2026")
        self.assertEqual(enqueue["context"]["note"], "Under review at JGR Atmospheres")
        self.assertEqual(
            self.audit.record.call_args.kwargs["event_type"],
            AccessEventType.INVITATION_CREATED,
        )

    def test_an_invitation_to_a_dataset_without_an_embargo_leaves_the_embargo_out(self):
        self.dataset.embargo_until = None

        self.service.grant(
            self.dataset.id,
            CALLER,
            GrantRequest(level="read", email="dora@ufam.edu.br"),
        )

        context = self.email.enqueue.call_args.kwargs["context"]
        self.assertIsNone(context["embargo_until_date"])
        self.assertIsNone(context["note"])

    def test_an_orcid_invitation_sends_no_email(self):
        result = self.service.grant(
            self.dataset.id,
            CALLER,
            GrantRequest(level="read", orcid="0000-0002-1825-0097"),
        )
        self.assertEqual(result.kind, "invitation")
        self.email.enqueue.assert_not_called()

    def test_a_second_pending_invitation_for_the_same_person_is_refused(self):
        self.invitations.find_pending.return_value = SimpleNamespace(id=uuid4())
        with self.assertRaises(BadRequestException) as caught:
            self.service.grant(
                self.dataset.id,
                CALLER,
                GrantRequest(level="read", email="dora@ufam.edu.br"),
            )
        self.assertEqual(caught.exception.errors[0].code, "already_has_access")


class TestManage(ShareServiceTestCase):
    def test_revoking_a_permission_goes_through_the_permission_service(self):
        self.permission_service.revoke.return_value = True
        target = uuid4()

        self.service.revoke_permission(self.dataset.id, CALLER, target)

        self.permission_service.revoke.assert_called_once_with(
            self.dataset.id, target, CALLER
        )

    def test_revoking_a_missing_permission_is_not_found(self):
        with self.assertRaises(NotFoundException):
            self.service.revoke_permission(self.dataset.id, CALLER, uuid4())

    def test_regenerating_a_link_replaces_the_token(self):
        invitation_id = uuid4()
        self.invitations.fetch.return_value = SimpleNamespace(
            id=invitation_id, accepted_at=None, revoked_at=None
        )
        self.invitations.replace_token.return_value = True

        link = self.service.regenerate_link(self.dataset.id, CALLER, invitation_id)

        token = link.rsplit("/", 1)[1]
        self.invitations.replace_token.assert_called_once_with(
            invitation_id, hash_token(token)
        )

    def test_a_used_invitation_cannot_get_a_new_link(self):
        self.invitations.fetch.return_value = SimpleNamespace(
            id=uuid4(), accepted_at=NOW, revoked_at=None
        )
        with self.assertRaises(NotFoundException):
            self.service.regenerate_link(self.dataset.id, CALLER, uuid4())

    def test_revoking_a_pending_invitation_stamps_it_and_records_the_event(self):
        invitation_id = uuid4()
        self.invitations.fetch.return_value = SimpleNamespace(
            id=invitation_id, accepted_at=None, revoked_at=None
        )

        self.service.revoke_invitation(self.dataset.id, CALLER, invitation_id)

        self.invitations.revoke.assert_called_once_with(invitation_id, NOW)
        self.assertEqual(
            self.audit.record.call_args.kwargs["event_type"],
            AccessEventType.INVITATION_REVOKED,
        )

    def test_an_accepted_invitation_is_not_revoked_its_permission_is(self):
        self.invitations.fetch.return_value = SimpleNamespace(
            id=uuid4(), accepted_at=NOW, revoked_at=None
        )

        with self.assertRaises(NotFoundException):
            self.service.revoke_invitation(self.dataset.id, CALLER, uuid4())

        self.invitations.revoke.assert_not_called()

    def test_candidates_need_two_characters(self):
        self.assertEqual(self.service.candidates(self.dataset.id, CALLER, "a"), [])
        self.users.search_share_candidates.assert_not_called()

    def test_candidates_exclude_the_owner_and_current_permissions(self):
        holder = uuid4()
        self.permissions.list_for_dataset.return_value = [
            SimpleNamespace(user_id=holder)
        ]
        self.users.search_share_candidates.return_value = [user_row(name="Ana Lima")]

        found = self.service.candidates(self.dataset.id, CALLER, "ana")

        self.assertEqual([user.name for user in found], ["Ana Lima"])
        self.users.search_share_candidates.assert_called_once_with(
            tenancy=self.dataset.tenancy, term="ana", exclude_ids=[OWNER, holder]
        )
