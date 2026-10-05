import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, call
from uuid import uuid4
from app.exception.not_found import NotFoundException
from app.model.tenancy import DEFAULT_TENANCY, TenancyEventType
from app.model.user import User, UserProvider
from app.model.db.user import User as UserDBModel, Provider as ProviderDBModel
from app.model.db.tenancy import Tenancy as TenancyDBModel
from app.repository.tenancy import TenancyRepository
from app.repository.tenancy_event import TenancyEventRepository
from app.repository.user import UserRepository
from app.service.email_template import EmailTemplate
from app.service.user import UserService
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

        self.tenancy_repository.fetch.assert_any_call(
            tenancy="datamap/production/data-amazon"
        )
        created = self.user_repository.upsert.call_args.kwargs["user"]
        self.assertIn(existing_tenancy, created.tenancies)

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


class TestDefaultAccess(unittest.TestCase):
    def setUp(self):
        self.user_repository = Mock(spec=UserRepository)
        self.tenancy_repository = Mock(spec=TenancyRepository)
        self.tenancy_repository.fetch.side_effect = lambda tenancy: TenancyDBModel(
            name=tenancy, is_enabled=True
        )
        self.casbin_enforcer = Mock(spec=SyncedEnforcer)
        self.events = Mock(spec=TenancyEventRepository)
        self.user_id = uuid4()
        persisted = Mock(spec=UserDBModel)
        persisted.id = self.user_id
        self.user_repository.upsert.return_value = persisted
        self.service = UserService(
            self.user_repository,
            self.tenancy_repository,
            self.casbin_enforcer,
            tenancy_events=self.events,
        )

    def account(self, **overrides) -> User:
        values = dict(
            name="Ana Souza", email="ana.souza@usp.br", providers=[], roles=[]
        )
        values.update(overrides)
        return User(**values)

    def created(self) -> UserDBModel:
        return self.user_repository.upsert.call_args.kwargs["user"]

    def test_a_new_account_is_in_public(self):
        self.service.create(self.account())

        self.assertEqual([t.name for t in self.created().tenancies], [DEFAULT_TENANCY])

    def test_public_comes_after_the_tenancies_given_and_only_once(self):
        self.service.create(
            self.account(tenancies=["datamap/production/data-amazon", DEFAULT_TENANCY])
        )

        self.assertEqual(
            [t.name for t in self.created().tenancies],
            ["datamap/production/data-amazon", DEFAULT_TENANCY],
        )

    def test_a_new_account_can_work_at_once(self):
        self.service.create(self.account())

        self.casbin_enforcer.add_grouping_policy.assert_called_once_with(
            str(self.user_id), "datasets_write"
        )

    def test_datasets_write_is_added_to_the_roles_given_once(self):
        self.service.create(self.account(roles=["admin", "datasets_write"]))

        self.assertEqual(
            self.casbin_enforcer.add_grouping_policy.call_args_list,
            [
                call(str(self.user_id), "admin"),
                call(str(self.user_id), "datasets_write"),
            ],
        )

    def test_every_membership_is_recorded_with_no_actor(self):
        self.service.create(self.account(tenancies=["datamap/production/data-amazon"]))

        self.assertEqual(
            self.events.append.call_args_list,
            [
                call(
                    tenancy="datamap/production/data-amazon",
                    event_type=TenancyEventType.MEMBER_ADDED,
                    user_id=self.user_id,
                ),
                call(
                    tenancy=DEFAULT_TENANCY,
                    event_type=TenancyEventType.MEMBER_ADDED,
                    user_id=self.user_id,
                ),
            ],
        )

    def test_a_failure_to_record_does_not_undo_the_account(self):
        self.events.append.side_effect = RuntimeError("database gone")

        with self.assertLogs("service:UserService", level="ERROR"):
            user_id = self.service.create(self.account())

        self.assertEqual(user_id, self.user_id)

    def test_an_account_created_with_a_password_is_stored_confirmed(self):
        self.service.create(
            self.account(), password_hash=BCRYPT_LIKE, email_verified_at=CREATED
        )

        self.assertEqual(self.created().password_hash, BCRYPT_LIKE)
        self.assertEqual(self.created().email_verified_at, CREATED)

    def test_nobody_is_emailed_about_a_new_account_any_more(self):
        self.assertNotIn("new_account_pending", [t.value for t in EmailTemplate])


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
