from uuid import UUID
from app.exception.NotFoundException import NotFoundException
from app.model.db.user import Provider as ProviderDBModel, User as UserDBModel
from app.model.db.tenancy import Tenancy as TenancyDBModel
from app.model.user import User, UserProvider, UserQuery
from app.repository.tenancy import TenancyRepository
from app.repository.user import UserRepository
from werkzeug.exceptions import NotFound
from casbin import SyncedEnforcer


class UserService:
    def __init__(
        self,
        repository: UserRepository,
        tenancy_repository: TenancyRepository,
        casbin_enforcer: SyncedEnforcer,
    ) -> None:
        self._repository: UserRepository = repository
        self._tenancy_repository: TenancyRepository = tenancy_repository
        self._casbin_enforcer: SyncedEnforcer = casbin_enforcer

    def __adapt_user(self, user: UserDBModel) -> User:
        return User(
            id=user.id,
            name=user.name,
            email=user.email,
            roles=user.roles,
            is_enabled=user.is_enabled,
            providers=[
                UserProvider(name=provider.name, reference=provider.reference)
                for provider in user.providers
            ],
            tenancies=[tenancy.name for tenancy in user.tenancies],
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    def fetch_by_id(self, id: UUID, is_enabled: bool = True) -> User:
        user: UserDBModel = self._repository.fetch_by_id(id, is_enabled)
        if user is None:
            raise NotFoundException(f"not_found: {id}")
        user.roles = self._casbin_enforcer.get_roles_for_user(str(user.id))
        return self.__adapt_user(user)

    def fetch_by_email(self, email: str, is_enabled: bool = True) -> User:
        user: UserDBModel = self._repository.fetch_by_email(email, is_enabled)
        if user is None:
            raise NotFound(f"User with email {email} not found")
        user.roles = self._casbin_enforcer.get_roles_for_user(str(user.id))
        return self.__adapt_user(user)

    def fetch_by_provider(
        self, provider_name: str, reference: str, is_enabled: bool = True
    ) -> User:
        user: UserDBModel = self._repository.fetch_by_provider(
            provider_name, reference, is_enabled
        )
        if user is None:
            raise NotFoundException(f"not_found: {provider_name} {reference}")
        user.roles = self._casbin_enforcer.get_roles_for_user(str(user.id))
        return self.__adapt_user(user)

    def create(self, user: User) -> UUID:
        user = UserDBModel(name=user.name, email=user.email)

        for provider in user.providers:
            user.providers.append(
                ProviderDBModel(name=provider.name, reference=provider.reference)
            )

        for tenancy in user.tenancies:
            user.tenancies.append(TenancyDBModel(name=tenancy, is_enabled=True))

        user_id = self._repository.upsert(user).id

        for role in user.roles:
            self._casbin_enforcer.add_grouping_policy(str(user.id), role)

        return user_id

    def update(self, id: UUID, name: str, email: str) -> None:
        user: UserDBModel = self._repository.fetch_by_id(id)
        if user is None:
            raise NotFoundException(f"not_found: {id}")
        user.name = name
        user.email = email
        self._repository.upsert(user)

    def add_roles(self, id: UUID, roles: list[str]) -> None:
        user: UserDBModel = self._repository.fetch_by_id(id)
        if user is None:
            raise NotFoundException(f"not_found: {id}")
        for role in roles:
            self._casbin_enforcer.add_role_for_user(id, role)

    def remove_roles(self, id: UUID, roles: list[str]) -> None:
        user: UserDBModel = self._repository.fetch_by_id(id)
        if user is None:
            raise NotFoundException(f"not_found: {id}")
        for role in roles:
            self._casbin_enforcer.delete_role_for_user(id, role)

    def add_provider(self, id: UUID, provider: str, reference: str) -> None:
        user: UserDBModel = self._repository.fetch_by_id(id)
        if user is None:
            raise NotFoundException(f"not_found: {id}")
        user.providers.append(ProviderDBModel(name=provider, reference=reference))
        self._repository.upsert(user)

    def remove_provider(self, id: UUID, provider_name: str, reference: str) -> None:
        user: UserDBModel = self._repository.fetch_by_id(id)
        if user is None:
            raise NotFoundException(f"not_found: {id}")
        for provider in user.providers:
            if provider.name == provider_name and provider.reference == reference:
                user.providers.remove(provider)
                break
        self._repository.upsert(user)

    def disable(self, id: UUID) -> None:
        user: UserDBModel = self._repository.fetch_by_id(id)
        if user is None:
            raise NotFoundException(f"not_found: {id}")
        user.is_enabled = False
        self._repository.upsert(user)

    def enable(self, id: UUID) -> None:
        user: UserDBModel = self._repository.fetch_by_id(id, False)
        if user is None:
            raise NotFoundException(f"not_found: {id}")
        user.is_enabled = True
        self._repository.upsert(user)

    def search(self, query_params: UserQuery) -> list[User]:
        users: list[User] = []

        for db_user in self._repository.search(query_params):
            db_user.roles = self._casbin_enforcer.get_implicit_roles_for_user(
                str(db_user.id)
            )
            users.append(self.__adapt_user(user=db_user))

        return users

    def enforce(self, user_id: UUID, resource: str, action: str) -> bool:
        return self._casbin_enforcer.enforce(str(user_id), resource, action)

    def load_policy(self) -> bool:
        return self._casbin_enforcer.load_policy()

    def add_tenancies(self, user_id: UUID, tenancies: list[str]) -> None:
        # TODO check editor has the access to the tenancy
        user: UserDBModel = self._repository.fetch_by_id(user_id)
        if user is None:
            raise NotFoundException(f"not_found: {user_id}")
        for tenancy in tenancies:
            # Only way I found to make this work with pre-existing tenancy data
            existing_tenancy = self._tenancy_repository.fetch(tenancy)
            user.tenancies.append(existing_tenancy)
        self._repository.upsert(user)

    def remove_tenancies(self, user_id: UUID, tenancies: list[str]) -> None:
        # TODO check editor has the access to the tenancy
        user: UserDBModel = self._repository.fetch_by_id(user_id)
        if user is None:
            raise NotFound(f"User {user_id} not found")
        for existing_tenancy in user.tenancies:
            for tenancy in tenancies:
                if existing_tenancy.name == tenancy:
                    # Only way I found to make this work with pre-existing tenancy data
                    database_tenancy = self._tenancy_repository.fetch(tenancy)
                    user.tenancies.remove(database_tenancy)
                    break
        self._repository.upsert(user)
