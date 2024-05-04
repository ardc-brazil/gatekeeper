import logging
from app.model.user import Provider, User
from app.repository.tenancy import TenancyRepository
from app.repository.user import UserRepository
from werkzeug.exceptions import NotFound
from controller.interceptor.authorization_container import AuthorizationContainer

repository = UserRepository()
tenancy_repository = TenancyRepository()


class UserService:
    def __adapt_user(self, user):
        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "roles": user.roles,
            "is_enabled": user.is_enabled,
            "providers": user.providers,
            "tenancies": [tenancy.name for tenancy in user.tenancies],
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }

    def fetch_by_id(self, id, is_enabled=True):
        user = repository.fetch_by_id(id, is_enabled)
        if user is None:
            raise NotFound(f"User with id {id} not found")
        user.roles = (
            AuthorizationContainer.instance()
            .getEnforcer()
            .get_roles_for_user(str(user.id))
        )
        return self.__adapt_user(user)

    def fetch_by_email(self, email, is_enabled=True):
        user = repository.fetch_by_email(email, is_enabled)
        if user is None:
            raise NotFound(f"User with email {email} not found")
        user.roles = (
            AuthorizationContainer.instance()
            .getEnforcer()
            .get_roles_for_user(str(user.id))
        )
        return self.__adapt_user(user)

    def fetch_by_provider(self, provider_name, reference, is_enabled=True):
        user = repository.fetch_by_provider(provider_name, reference, is_enabled)
        if user is None:
            raise NotFound(
                f"User with provider {provider_name} and reference {reference} not found"
            )
        user.roles = (
            AuthorizationContainer.instance()
            .getEnforcer()
            .get_roles_for_user(str(user.id))
        )
        return self.__adapt_user(user)

    def create(self, request_body):
        try:
            user = User(name=request_body["name"], email=request_body["email"])

            if "providers" in request_body:
                for provider in request_body["providers"]:
                    user.providers.append(
                        Provider(
                            name=provider["name"], reference=provider["reference"]
                        )
                    )

            user_id = repository.upsert(user).id

            if "roles" in request_body:
                for role in request_body["roles"]:
                    AuthorizationContainer.instance().getEnforcer().add_grouping_policy(
                        str(user.id), role
                    )

            return user_id
        except Exception as e:
            logging.error(e)
            raise e

    def update(self, id, request_body):
        try:
            user = repository.fetch_by_id(id)
            if user is None:
                raise NotFound(f"User {id} not found")
            user.name = request_body["name"]
            user.email = request_body["email"]
            repository.upsert(user)
        except Exception as e:
            logging.error(e)
            raise e

    def add_roles(self, id, roles):
        try:
            user = repository.fetch_by_id(id)
            if user is None:
                raise NotFound(f"User {id} not found")
            for role in roles:
                AuthorizationContainer.instance().getEnforcer().add_role_for_user(
                    id, role
                )
        except Exception as e:
            logging.error(e)
            raise e

    def remove_roles(self, id, roles):
        try:
            user = repository.fetch_by_id(id)
            if user is None:
                raise NotFound(f"User {id} not found")
            for role in roles:
                AuthorizationContainer.instance().getEnforcer().delete_role_for_user(
                    id, role
                )
        except Exception as e:
            logging.error(e)
            raise e

    def add_provider(self, id, provider, reference):
        try:
            user = repository.fetch_by_id(id)
            if user is None:
                raise NotFound(f"User {id} not found")
            user.providers.append(Provider(name=provider, reference=reference))
            repository.upsert(user)
        except Exception as e:
            logging.error(e)
            raise e

    def remove_provider(self, id, provider_name, reference):
        try:
            user = repository.fetch_by_id(id)
            if user is None:
                raise NotFound(f"User {id} not found")
            for provider in user.providers:
                if provider.name == provider_name and provider.reference == reference:
                    user.providers.remove(provider)
                    break
            repository.upsert(user)
        except Exception as e:
            logging.error(e)
            raise e

    def disable(self, id):
        try:
            user = repository.fetch_by_id(id)
            if user is None:
                raise NotFound(f"User {id} not found")
            user.is_enabled = False
            repository.upsert(user)
        except Exception as e:
            logging.error(e)
            raise e

    def enable(self, id):
        try:
            user = repository.fetch_by_id(id, False)
            if user is None:
                raise NotFound(f"User {id} not found")
            user.is_enabled = True
            repository.upsert(user)
        except Exception as e:
            logging.error(e)
            raise e

    def search(self, query_params):
        users = []

        for user in repository.search(query_params):
            user.roles = (
                AuthorizationContainer.instance()
                .getEnforcer()
                .get_implicit_roles_for_user(str(user.id))
            )
            users.append(self.__adapt_user(user))

        return users

    def enforce(self, user_id, resource, action) -> bool:
        return (
            AuthorizationContainer.instance()
            .getEnforcer()
            .enforce(user_id, resource, action)
        )

    def load_policy(self) -> bool:
        return AuthorizationContainer.instance().getEnforcer().load_policy()

    def add_tenancies(self, user_id, tenancies):
        try:
            # TODO check editor has the access to the tenancy
            user = repository.fetch_by_id(user_id)
            if user is None:
                raise NotFound(f"User {user_id} not found")
            for tenancy in tenancies:
                # Only way I found to make this work with pre-existing tenancy data
                existing_tenancy = tenancy_repository.fetch(tenancy)
                user.tenancies.append(existing_tenancy)
            repository.upsert(user)
        except Exception as e:
            logging.error(e)
            raise e

    def remove_tenancies(self, user_id, tenancies):
        try:
            # TODO check editor has the access to the tenancy
            user = repository.fetch_by_id(user_id)
            if user is None:
                raise NotFound(f"User {user_id} not found")
            for existing_tenancy in user.tenancies:
                for tenancy in tenancies:
                    if existing_tenancy.name == tenancy:
                        # Only way I found to make this work with pre-existing tenancy data
                        database_tenancy = tenancy_repository.fetch(tenancy)
                        user.tenancies.remove(database_tenancy)
                        break
            repository.upsert(user)
        except Exception as e:
            logging.error(e)
            raise e
