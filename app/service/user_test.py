import unittest
from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import uuid4
from app.exception.not_found import NotFoundException
from app.model.user import User, UserProvider
from app.model.db.user import User as UserDBModel, Provider as ProviderDBModel
from app.model.db.tenancy import Tenancy as TenancyDBModel
from app.repository.tenancy import TenancyRepository
from app.repository.user import UserRepository
from app.service.email import EmailService
from app.service.user import UserService, admin_addresses
from casbin import SyncedEnforcer


class TestUserService(unittest.TestCase):
    def setUp(self):
        self.user_repository = Mock(spec=UserRepository)
        self.tenancy_repository = Mock(spec=TenancyRepository)
        self.casbin_enforcer = Mock(spec=SyncedEnforcer)
        self.user_service = UserService(
            self.user_repository, self.tenancy_repository, self.casbin_enforcer
        )

    def test_fetch_by_id_success(self):
        user_id = uuid4()
        db_user = Mock(spec=UserDBModel)
        db_user.id = user_id
        db_user.roles = ["role1", "role2"]
        db_user.providers = [Mock(spec=ProviderDBModel)]
        db_user.tenancies = [Mock(spec=TenancyDBModel)]
        self.user_repository.fetch_by_id.return_value = db_user
        self.casbin_enforcer.get_roles_for_user.return_value = db_user.roles

        user = self.user_service.fetch_by_id(user_id)

        self.assertEqual(user.id, user_id)
        self.user_repository.fetch_by_id.assert_called_once_with(
            id=user_id, is_enabled=True
        )
        self.casbin_enforcer.get_roles_for_user.assert_called_once_with(str(user_id))

    def test_roles_of_reads_the_enforcer_without_loading_the_account(self):
        user_id = uuid4()
        self.casbin_enforcer.get_roles_for_user.return_value = ["admin"]

        self.assertEqual(self.user_service.roles_of(user_id), ["admin"])
        self.casbin_enforcer.get_roles_for_user.assert_called_once_with(str(user_id))
        self.user_repository.fetch_by_id.assert_not_called()

    def test_fetch_by_id_not_found(self):
        user_id = uuid4()
        self.user_repository.fetch_by_id.return_value = None

        with self.assertRaises(NotFoundException) as context:
            self.user_service.fetch_by_id(user_id)

        self.assertEqual(str(context.exception), f"not_found: {user_id}")
        self.user_repository.fetch_by_id.assert_called_once_with(
            id=user_id, is_enabled=True
        )

    def test_fetch_by_email_success(self):
        email = "test@example.com"
        db_user = Mock(spec=UserDBModel)
        db_user.id = uuid4()
        db_user.email = email
        db_user.roles = ["role1", "role2"]
        db_user.providers = [Mock(spec=ProviderDBModel)]
        db_user.tenancies = [Mock(spec=TenancyDBModel)]
        self.user_repository.fetch_by_email.return_value = db_user
        self.casbin_enforcer.get_roles_for_user.return_value = db_user.roles

        user = self.user_service.fetch_by_email(email)

        self.assertEqual(user.email, email)
        self.user_repository.fetch_by_email.assert_called_once_with(
            email=email, is_enabled=True
        )
        self.casbin_enforcer.get_roles_for_user.assert_called_once_with(str(db_user.id))

    def test_fetch_by_email_not_found(self):
        email = "test@example.com"
        self.user_repository.fetch_by_email.return_value = None

        with self.assertRaises(NotFoundException) as context:
            self.user_service.fetch_by_email(email)

        self.assertEqual(str(context.exception), f"not_found: {email}")
        self.user_repository.fetch_by_email.assert_called_once_with(
            email=email, is_enabled=True
        )

    def test_fetch_by_provider_success(self):
        provider_name = "google"
        reference = "12345"
        db_user = Mock(spec=UserDBModel)
        db_user.id = uuid4()
        db_user.roles = ["role1", "role2"]
        db_user.providers = [ProviderDBModel(name=provider_name, reference=reference)]
        db_user.tenancies = [Mock(spec=TenancyDBModel)]
        self.user_repository.fetch_by_provider.return_value = db_user
        self.casbin_enforcer.get_roles_for_user.return_value = db_user.roles

        user = self.user_service.fetch_by_provider(provider_name, reference)

        self.assertEqual(user.providers[0].name, provider_name)
        self.assertEqual(user.providers[0].reference, reference)
        self.user_repository.fetch_by_provider.assert_called_once_with(
            provider_name=provider_name, reference=reference, is_enabled=True
        )
        self.casbin_enforcer.get_roles_for_user.assert_called_once_with(str(db_user.id))

    def test_fetch_by_provider_not_found(self):
        provider_name = "google"
        reference = "12345"
        self.user_repository.fetch_by_provider.return_value = None

        with self.assertRaises(NotFoundException) as context:
            self.user_service.fetch_by_provider(provider_name, reference)

        self.assertEqual(
            str(context.exception), f"not_found: {provider_name} {reference}"
        )
        self.user_repository.fetch_by_provider.assert_called_once_with(
            provider_name=provider_name, reference=reference, is_enabled=True
        )

    def test_create_success(self):
        # Callers never send an id: UserCreateRequest carries only name, email,
        # roles and providers. The id exists only after the user is persisted,
        # so the roles must be bound to the persisted id, not to the input one.
        persisted_id = uuid4()
        user = User(
            name="Test User",
            email="test@example.com",
            roles=["role1", "role2"],
            providers=[UserProvider(name="google", reference="12345")],
            tenancies=["tenancy1"],
            is_enabled=True,
            created_at=None,
            updated_at=None,
        )
        db_user = Mock(spec=UserDBModel)
        db_user.id = persisted_id
        self.user_repository.upsert.return_value = db_user
        self.tenancy_repository.fetch.return_value = TenancyDBModel(
            name="tenancy1", is_enabled=True
        )

        created_id = self.user_service.create(user)

        self.assertEqual(created_id, persisted_id)
        self.user_repository.upsert.assert_called_once()
        self.casbin_enforcer.add_grouping_policy.assert_any_call(
            str(persisted_id), "role1"
        )
        self.casbin_enforcer.add_grouping_policy.assert_any_call(
            str(persisted_id), "role2"
        )

    def test_create_persists_the_tenancies_it_was_given(self):
        persisted_id = uuid4()
        existing_tenancy = TenancyDBModel(
            name="datamap/production/data-amazon", is_enabled=True
        )
        self.tenancy_repository.fetch.return_value = existing_tenancy
        db_user = Mock(spec=UserDBModel)
        db_user.id = persisted_id
        self.user_repository.upsert.return_value = db_user

        user = User(
            name="Test User",
            email="test@example.com",
            roles=[],
            providers=[],
            tenancies=["datamap/production/data-amazon"],
        )

        self.user_service.create(user)

        self.tenancy_repository.fetch.assert_called_once_with(
            tenancy="datamap/production/data-amazon"
        )
        created = self.user_repository.upsert.call_args.kwargs["user"]
        self.assertIn(existing_tenancy, created.tenancies)

    def test_remove_tenancies_success(self):
        user_id = uuid4()
        keep = Mock(spec=TenancyDBModel)
        keep.name = "keep-me"
        drop = Mock(spec=TenancyDBModel)
        drop.name = "drop-me"
        db_user = Mock(spec=UserDBModel)
        db_user.tenancies = [keep, drop]
        self.user_repository.fetch_by_id.return_value = db_user

        self.user_service.remove_tenancies(user_id=user_id, tenancies=["drop-me"])

        self.assertEqual(db_user.tenancies, [keep])
        self.user_repository.upsert.assert_called_once_with(user=db_user)

    def test_remove_tenancies_ignores_one_the_user_does_not_have(self):
        user_id = uuid4()
        keep = Mock(spec=TenancyDBModel)
        keep.name = "keep-me"
        db_user = Mock(spec=UserDBModel)
        db_user.tenancies = [keep]
        self.user_repository.fetch_by_id.return_value = db_user

        self.user_service.remove_tenancies(user_id=user_id, tenancies=["never-had-it"])

        self.assertEqual(db_user.tenancies, [keep])

    def test_update_success(self):
        user_id = uuid4()
        db_user = Mock(spec=UserDBModel)
        db_user.id = user_id
        db_user.providers = [Mock(spec=ProviderDBModel)]
        db_user.tenancies = [Mock(spec=TenancyDBModel)]
        self.user_repository.fetch_by_id.return_value = db_user
        self.user_repository.upsert.return_value = db_user
        self.casbin_enforcer.get_roles_for_user.return_value = []

        self.user_service.update(
            user_id, name="Updated Name", email="updated@example.com"
        )

        self.assertEqual(db_user.name, "Updated Name")
        self.assertEqual(db_user.email, "updated@example.com")
        self.user_repository.upsert.assert_called_once_with(db_user)
        self.user_repository.fetch_by_id.assert_called_once_with(id=user_id)
        self.casbin_enforcer.get_roles_for_user.assert_called_once_with(str(user_id))

    def test_update_not_found(self):
        user_id = uuid4()
        self.user_repository.fetch_by_id.return_value = None

        with self.assertRaises(NotFoundException) as context:
            self.user_service.update(
                user_id, name="Updated Name", email="updated@example.com"
            )

        self.assertEqual(str(context.exception), f"not_found: {user_id}")
        self.user_repository.fetch_by_id.assert_called_once_with(id=user_id)

    def test_add_roles_success(self):
        # Controllers hand over a UUID. Casbin stores subjects as strings, so a
        # raw UUID would never match on lookup.
        user_id = uuid4()
        db_user = Mock(spec=UserDBModel)
        self.user_repository.fetch_by_id.return_value = db_user

        roles = ["role1", "role2"]
        self.user_service.add_roles(user_id, roles)

        for role in roles:
            self.casbin_enforcer.add_role_for_user.assert_any_call(
                user=str(user_id), role=role
            )
        self.user_repository.fetch_by_id.assert_called_once_with(id=user_id)

    def test_add_roles_not_found(self):
        user_id = uuid4()
        self.user_repository.fetch_by_id.return_value = None

        roles = ["role1", "role2"]
        with self.assertRaises(NotFoundException) as context:
            self.user_service.add_roles(user_id, roles)

        self.assertEqual(str(context.exception), f"not_found: {user_id}")
        self.user_repository.fetch_by_id.assert_called_once_with(id=user_id)

    def test_remove_roles_success(self):
        user_id = uuid4()
        db_user = Mock(spec=UserDBModel)
        self.user_repository.fetch_by_id.return_value = db_user

        roles = ["role1", "role2"]
        self.user_service.remove_roles(user_id, roles)

        for role in roles:
            self.casbin_enforcer.delete_role_for_user.assert_any_call(
                user=str(user_id), role=role
            )
        self.user_repository.fetch_by_id.assert_called_once_with(id=user_id)

    def test_remove_roles_not_found(self):
        user_id = uuid4()
        self.user_repository.fetch_by_id.return_value = None

        roles = ["role1", "role2"]
        with self.assertRaises(NotFoundException) as context:
            self.user_service.remove_roles(user_id, roles)

        self.assertEqual(str(context.exception), f"not_found: {user_id}")
        self.user_repository.fetch_by_id.assert_called_once_with(id=user_id)

    def test_add_provider_success(self):
        user_id = uuid4()
        db_user = Mock(spec=UserDBModel)
        db_user.providers = []
        self.user_repository.fetch_by_id.return_value = db_user

        provider_name = "google"
        reference = "12345"
        self.user_service.add_provider(user_id, provider_name, reference)

        self.assertEqual(db_user.providers[0].name, provider_name)
        self.assertEqual(db_user.providers[0].reference, reference)
        self.user_repository.upsert.assert_called_once_with(user=db_user)
        self.user_repository.fetch_by_id.assert_called_once_with(id=user_id)

    def test_add_provider_not_found(self):
        user_id = uuid4()
        self.user_repository.fetch_by_id.return_value = None

        provider_name = "google"
        reference = "12345"
        with self.assertRaises(NotFoundException) as context:
            self.user_service.add_provider(user_id, provider_name, reference)

        self.assertEqual(str(context.exception), f"not_found: {user_id}")


CREATED = datetime(2026, 10, 3, 14, 5, tzinfo=timezone.utc)
BCRYPT_LIKE = "$2b$10$" + "x" * 53


class TestNewAccountNotification(unittest.TestCase):
    def setUp(self):
        self.user_repository = Mock(spec=UserRepository)
        self.tenancy_repository = Mock(spec=TenancyRepository)
        self.casbin_enforcer = Mock(spec=SyncedEnforcer)
        self.email_service = Mock(spec=EmailService)
        self.user_id = uuid4()
        persisted = Mock(spec=UserDBModel)
        persisted.id = self.user_id
        persisted.created_at = CREATED
        self.user_repository.upsert.return_value = persisted

    def service(self, admin_emails: str) -> UserService:
        return UserService(
            self.user_repository,
            self.tenancy_repository,
            self.casbin_enforcer,
            email_service=self.email_service,
            admin_emails=admin_emails,
        )

    def orcid_user(self) -> User:
        return User(
            name="Ana Souza",
            email="ana.souza@usp.br",
            providers=[UserProvider(name="orcid", reference="0000-0002-1825-0097")],
            roles=[],
        )

    def sent(self) -> list[dict]:
        return [call.kwargs for call in self.email_service.enqueue.call_args_list]

    def test_every_admin_is_told_about_a_new_account(self):
        self.service("admin.one@usp.br, admin.two@usp.br").create(self.orcid_user())

        self.assertEqual(
            [kwargs["recipient"] for kwargs in self.sent()],
            ["admin.one@usp.br", "admin.two@usp.br"],
        )

    def test_the_message_names_the_account_and_how_it_signs_in(self):
        self.service("admin.one@usp.br").create(self.orcid_user())

        (kwargs,) = self.sent()
        self.assertEqual(kwargs["template"], "new_account_pending")
        self.assertEqual(
            kwargs["context"],
            {
                "name": "Ana Souza",
                "email": "ana.souza@usp.br",
                "sign_in_method": "ORCID",
                "created_at": "October 3, 2026 at 14:05 UTC",
            },
        )
        self.assertEqual(kwargs["related_type"], "user")
        self.assertEqual(kwargs["related_id"], self.user_id)
        self.assertTrue(
            kwargs["dedup_key"].startswith(f"new_account_pending:{self.user_id}:")
        )
        self.assertLessEqual(len(kwargs["dedup_key"]), 256)

    def test_each_admin_has_a_dedup_key_of_its_own(self):
        self.service("admin.one@usp.br,admin.two@usp.br").create(self.orcid_user())

        keys = {kwargs["dedup_key"] for kwargs in self.sent()}
        self.assertEqual(len(keys), 2)

    def test_an_account_created_with_a_password_is_stored_confirmed_and_says_so(self):
        self.service("admin.one@usp.br").create(
            User(name="Ana Souza", email="ana.souza@usp.br", providers=[], roles=[]),
            password_hash=BCRYPT_LIKE,
            email_verified_at=CREATED,
        )

        created = self.user_repository.upsert.call_args.kwargs["user"]
        self.assertEqual(created.password_hash, BCRYPT_LIKE)
        self.assertEqual(created.email_verified_at, CREATED)
        self.assertEqual(
            self.sent()[0]["context"]["sign_in_method"], "Email and password"
        )

    def test_an_account_created_through_the_api_without_a_provider_says_so(self):
        self.service("admin.one@usp.br").create(
            User(name="Ana Souza", email="ana.souza@usp.br", providers=[], roles=[])
        )

        self.assertEqual(
            self.sent()[0]["context"]["sign_in_method"], "Created through the API"
        )

    def test_nobody_is_told_when_the_list_is_empty(self):
        self.service("").create(self.orcid_user())

        self.email_service.enqueue.assert_not_called()

    def test_a_failure_to_queue_does_not_undo_the_account(self):
        self.email_service.enqueue.side_effect = RuntimeError("database gone")

        with self.assertLogs("service:UserService", level="ERROR"):
            user_id = self.service("admin.one@usp.br").create(self.orcid_user())

        self.assertEqual(user_id, self.user_id)


class TestAdminAddresses(unittest.TestCase):
    def test_a_comma_separated_list_is_split_and_trimmed(self):
        self.assertEqual(
            admin_addresses(" a@usp.br , b@usp.br,, "), ["a@usp.br", "b@usp.br"]
        )

    def test_an_empty_value_is_nobody(self):
        self.assertEqual(admin_addresses(""), [])


class TestCredentialFields(unittest.TestCase):
    def setUp(self):
        self.user_repository = Mock(spec=UserRepository)
        self.casbin_enforcer = Mock(spec=SyncedEnforcer)
        self.casbin_enforcer.get_roles_for_user.return_value = []
        self.service = UserService(
            self.user_repository, Mock(spec=TenancyRepository), self.casbin_enforcer
        )

    def test_a_user_says_whether_it_has_a_password_and_when_its_email_was_confirmed(
        self,
    ):
        user_id = uuid4()
        self.user_repository.fetch_by_id.return_value = UserDBModel(
            id=user_id,
            name="Ana Souza",
            email="ana.souza@usp.br",
            is_enabled=True,
            password_hash=BCRYPT_LIKE,
            email_verified_at=CREATED,
        )

        user = self.service.fetch_by_id(user_id)

        self.assertTrue(user.has_password)
        self.assertEqual(user.email_verified_at, CREATED)

    def test_an_account_without_either_says_so(self):
        user_id = uuid4()
        self.user_repository.fetch_by_id.return_value = UserDBModel(
            id=user_id, name="Ana Souza", email="ana.souza@usp.br", is_enabled=True
        )

        user = self.service.fetch_by_id(user_id)

        self.assertFalse(user.has_password)
        self.assertIsNone(user.email_verified_at)

    def test_a_new_address_is_no_longer_confirmed(self):
        db_user = UserDBModel(
            id=uuid4(),
            name="Ana Souza",
            email="ana.souza@usp.br",
            is_enabled=True,
            email_verified_at=CREATED,
        )
        self.user_repository.fetch_by_id.return_value = db_user
        self.user_repository.upsert.return_value = db_user

        self.service.update(db_user.id, name="Ana Souza", email="ana@ufam.edu.br")

        self.assertIsNone(db_user.email_verified_at)

    def test_the_same_address_in_another_case_stays_confirmed(self):
        db_user = UserDBModel(
            id=uuid4(),
            name="Ana Souza",
            email="ana.souza@usp.br",
            is_enabled=True,
            email_verified_at=CREATED,
        )
        self.user_repository.fetch_by_id.return_value = db_user
        self.user_repository.upsert.return_value = db_user

        self.service.update(db_user.id, name="Ana Souza", email="Ana.Souza@USP.br")

        self.assertEqual(db_user.email_verified_at, CREATED)
