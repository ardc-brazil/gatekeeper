import logging
from datetime import datetime, timezone
from uuid import UUID
from app.exception.not_found import NotFoundException
from app.logging_config import fields
from app.model.db.user import Provider as ProviderDBModel, User as UserDBModel
from app.model.user import User, UserProvider, UserQuery
from app.repository.tenancy import TenancyRepository
from app.repository.user import UserRepository
from app.service.email import EmailService
from app.service.email_format import long_date
from app.service.email_template import EmailTemplate
from app.service.share_token import hash_token
from casbin import SyncedEnforcer

PROVIDER_LABELS = {"orcid": "ORCID", "github": "GitHub"}


def admin_addresses(value: str) -> list[str]:
    return [address.strip() for address in (value or "").split(",") if address.strip()]


def sign_in_method(providers: list, has_password: bool) -> str:
    if has_password:
        return "Email and password"
    if providers:
        return ", ".join(
            PROVIDER_LABELS.get(provider.name, provider.name) for provider in providers
        )
    return "Created through the API"


def created_on(moment: datetime) -> str:
    utc = moment.astimezone(timezone.utc)
    return f"{long_date(utc)} at {utc:%H:%M} UTC"


class UserService:
    def __init__(
        self,
        repository: UserRepository,
        tenancy_repository: TenancyRepository,
        casbin_enforcer: SyncedEnforcer,
        email_service: EmailService | None = None,
        admin_emails: str = "",
    ) -> None:
        self._repository: UserRepository = repository
        self._tenancy_repository: TenancyRepository = tenancy_repository
        self._casbin_enforcer: SyncedEnforcer = casbin_enforcer
        self._email = email_service
        self._admin_emails = admin_addresses(admin_emails)
        self._logger = logging.getLogger("service:UserService")

    def __adapt_user(self, user: UserDBModel) -> User:
        return User(
            id=user.id,
            name=user.name,
            email=user.email,
            roles=user.roles if hasattr(user, "roles") else [],
            is_enabled=user.is_enabled,
            providers=[
                UserProvider(name=provider.name, reference=provider.reference)
                for provider in user.providers
            ],
            tenancies=[tenancy.name for tenancy in user.tenancies],
            created_at=user.created_at,
            updated_at=user.updated_at,
            email_verified_at=user.email_verified_at,
            has_password=user.password_hash is not None,
        )

    def fetch_by_id(self, id: UUID, is_enabled: bool = True) -> User:
        user: UserDBModel = self._repository.fetch_by_id(id=id, is_enabled=is_enabled)
        if user is None:
            raise NotFoundException(f"not_found: {id}")
        user.roles = self._casbin_enforcer.get_roles_for_user(str(user.id))
        return self.__adapt_user(user=user)

    def fetch_by_email(self, email: str, is_enabled: bool = True) -> User:
        user: UserDBModel = self._repository.fetch_by_email(
            email=email, is_enabled=is_enabled
        )
        if user is None:
            raise NotFoundException(f"not_found: {email}")
        user.roles = self._casbin_enforcer.get_roles_for_user(str(user.id))
        return self.__adapt_user(user=user)

    def fetch_by_provider(
        self, provider_name: str, reference: str, is_enabled: bool = True
    ) -> User:
        user: UserDBModel = self._repository.fetch_by_provider(
            provider_name=provider_name,
            reference=reference,
            is_enabled=is_enabled,
        )
        if user is None:
            raise NotFoundException(f"not_found: {provider_name} {reference}")
        user.roles = self._casbin_enforcer.get_roles_for_user(str(user.id))
        return self.__adapt_user(user=user)

    def create(
        self,
        user: User,
        password_hash: str | None = None,
        email_verified_at: datetime | None = None,
    ) -> UUID:
        dbUser = UserDBModel(
            name=user.name,
            email=user.email,
            password_hash=password_hash,
            email_verified_at=email_verified_at,
        )

        for provider in user.providers:
            dbUser.providers.append(
                ProviderDBModel(name=provider.name, reference=provider.reference)
            )

        for tenancy in user.tenancies or []:
            dbUser.tenancies.append(self._tenancy_repository.fetch(tenancy=tenancy))

        created = self._repository.upsert(user=dbUser)
        user_id = created.id

        for role in user.roles:
            self._casbin_enforcer.add_grouping_policy(str(user_id), role)

        self._notify_admins(
            user_id, user, created.created_at, password_hash is not None
        )
        return user_id

    def _notify_admins(
        self, user_id: UUID, user: User, created_at: datetime, has_password: bool
    ) -> None:
        if self._email is None:
            return
        for recipient in self._admin_emails:
            try:
                self._email.enqueue(
                    template=EmailTemplate.NEW_ACCOUNT_PENDING.value,
                    recipient=recipient,
                    context={
                        "name": user.name,
                        "email": user.email,
                        "sign_in_method": sign_in_method(
                            user.providers or [], has_password
                        ),
                        "created_at": created_on(created_at),
                    },
                    related_type="user",
                    related_id=user_id,
                    dedup_key=f"new_account_pending:{user_id}:{hash_token(recipient.lower())[:16]}",
                )
            except Exception:
                self._logger.error(
                    "email enqueue failed",
                    exc_info=True,
                    extra=fields(
                        template=EmailTemplate.NEW_ACCOUNT_PENDING.value,
                        user_id=str(user_id),
                    ),
                )

    def update(self, id: UUID, name: str, email: str) -> User:
        user: UserDBModel = self._repository.fetch_by_id(id=id)
        if user is None:
            raise NotFoundException(f"not_found: {id}")

        if (user.email or "").lower() != (email or "").lower():
            user.email_verified_at = None
        user.name = name
        user.email = email

        updated_user = self._repository.upsert(user)
        # Set roles attribute for the adapted user
        updated_user.roles = self._casbin_enforcer.get_roles_for_user(
            str(updated_user.id)
        )
        return self.__adapt_user(updated_user)

    def add_roles(self, id: UUID, roles: list[str]) -> None:
        user: UserDBModel = self._repository.fetch_by_id(id=id)
        if user is None:
            raise NotFoundException(f"not_found: {id}")
        for role in roles:
            self._casbin_enforcer.add_role_for_user(user=str(id), role=role)

    def remove_roles(self, id: UUID, roles: list[str]) -> None:
        user: UserDBModel = self._repository.fetch_by_id(id=id)
        if user is None:
            raise NotFoundException(f"not_found: {id}")
        for role in roles:
            self._casbin_enforcer.delete_role_for_user(user=str(id), role=role)

    def add_provider(self, id: UUID, provider: str, reference: str) -> None:
        user: UserDBModel = self._repository.fetch_by_id(id=id)
        if user is None:
            raise NotFoundException(f"not_found: {id}")
        user.providers.append(ProviderDBModel(name=provider, reference=reference))
        self._repository.upsert(user=user)

    def remove_provider(self, id: UUID, provider_name: str, reference: str) -> None:
        user: UserDBModel = self._repository.fetch_by_id(id=id)
        if user is None:
            raise NotFoundException(f"not_found: {id}")
        for provider in user.providers:
            if provider.name == provider_name and provider.reference == reference:
                user.providers.remove(provider)
                break
        self._repository.upsert(user=user)

    def disable(self, id: UUID) -> None:
        user: UserDBModel = self._repository.fetch_by_id(id=id)
        if user is None:
            raise NotFoundException(f"not_found: {id}")
        user.is_enabled = False
        self._repository.upsert(user=user)

    def enable(self, id: UUID) -> None:
        user: UserDBModel = self._repository.fetch_by_id(id=id, is_enabled=False)
        if user is None:
            raise NotFoundException(f"not_found: {id}")
        user.is_enabled = True
        self._repository.upsert(user=user)

    def search(self, query_params: UserQuery) -> list[User]:
        users: list[User] = []

        for db_user in self._repository.search(query_params=query_params):
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
        # TODO: Only admins should have permission to add user to a tenancy
        user: UserDBModel = self._repository.fetch_by_id(id=user_id)
        if user is None:
            raise NotFoundException(f"not_found: {user_id}")
        for tenancy in tenancies:
            # Only way I found to make this work with pre-existing tenancy data
            existing_tenancy = self._tenancy_repository.fetch(tenancy=tenancy)
            user.tenancies.append(existing_tenancy)
        self._repository.upsert(user=user)

    def remove_tenancies(self, user_id: UUID, tenancies: list[str]) -> None:
        # TODO check editor has the access to the tenancy
        # TODO: Only admins should have permission to add user to a tenancy
        user: UserDBModel = self._repository.fetch_by_id(id=user_id)
        if user is None:
            raise NotFoundException(f"not_found: {user_id}")
        to_remove = set(tenancies)
        user.tenancies = [
            tenancy for tenancy in user.tenancies if tenancy.name not in to_remove
        ]

        self._repository.upsert(user=user)
