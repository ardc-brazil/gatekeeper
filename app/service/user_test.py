import unittest
from unittest.mock import Mock
from uuid import uuid4
from app.exception.not_found import NotFoundException
from app.model.user import User, UserProvider
from app.model.db.user import User as UserDBModel, Provider as ProviderDBModel
from app.model.db.tenancy import Tenancy as TenancyDBModel
from app.repository.tenancy import TenancyRepository
from app.repository.user import UserRepository
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
        user = User(
            id=uuid4(),
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
        db_user.id = user.id
        self.user_repository.upsert.return_value = db_user

        created_id = self.user_service.create(user)

        self.assertEqual(created_id, user.id)
        self.user_repository.upsert.assert_called_once()
        self.casbin_enforcer.add_grouping_policy.assert_any_call(str(user.id), "role1")
        self.casbin_enforcer.add_grouping_policy.assert_any_call(str(user.id), "role2")

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
        user_id = str(uuid4())
        db_user = Mock(spec=UserDBModel)
        self.user_repository.fetch_by_id.return_value = db_user

        roles = ["role1", "role2"]
        self.user_service.add_roles(user_id, roles)

        for role in roles:
            self.casbin_enforcer.add_role_for_user.assert_any_call(
                user=user_id, role=role
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
                user=user_id, role=role
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
        with self.assertRaises(NotFoundException) as _:
            self.user_service.add_provider(user_id, provider_name, reference)

        self.assertEqual
