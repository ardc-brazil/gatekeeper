from typing import List
from app.model.db.tenancy import Tenancy as DBModel
from app.model.tenancy import (
    PRODUCTION_PREFIX,
    Tenancy,
    derived_display_name,
    is_default,
    is_production,
)
from app.repository.tenancy import TenancyRepository
from app.exception.conflict import ConflictException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.service.tenancy_membership import TenancyMembershipService


class TenancyService:
    def __init__(
        self,
        repository: TenancyRepository,
        membership_service: TenancyMembershipService,
    ) -> None:
        self._repository: TenancyRepository = repository
        self._membership_service = membership_service

    def __adapt_tenancy(self, tenancy: DBModel) -> Tenancy:
        return Tenancy(
            name=tenancy.name,
            is_enabled=tenancy.is_enabled,
            created_at=tenancy.created_at,
            updated_at=tenancy.updated_at,
        )

    def fetch(self, name: str, is_enabled: bool = True) -> Tenancy | None:
        res: DBModel = self._repository.fetch(tenancy=name, is_enabled=is_enabled)
        if res is None:
            return None
        tenancy: Tenancy = self.__adapt_tenancy(tenancy=res)
        return tenancy

    def fetch_all(self, is_enabled: bool = True) -> List[Tenancy]:
        res: DBModel = self._repository.fetch_all(is_enabled=is_enabled)
        if res is None:
            return []
        tenancies: List[Tenancy] = [
            self.__adapt_tenancy(tenancy=tenancy) for tenancy in res
        ]
        return tenancies

    def create(self, tenancy: Tenancy) -> None:
        if not is_production(tenancy.name):
            raise IllegalStateException("namespace_invalid")
        path, _ = self._membership_service.check_new_tenancy(
            derived_display_name(tenancy.name),
            tenancy.name[len(PRODUCTION_PREFIX) :],
        )
        self._repository.upsert(DBModel(name=path, is_enabled=tenancy.is_enabled))

    def update(self, old_name: str, updated_tenancy: Tenancy) -> None:
        if is_default(old_name):
            raise ConflictException("public_tenancy_locked")
        old_tenancy: DBModel = self._repository.fetch(tenancy=old_name)
        if old_tenancy is None:
            raise NotFoundException(f"not_found: {old_name}")

        old_tenancy.name = updated_tenancy.name
        old_tenancy.is_enabled = updated_tenancy.is_enabled
        self._repository.upsert(tenancy=old_tenancy)

    def disable(self, name: str) -> None:
        if is_default(name):
            raise ConflictException("public_tenancy_locked")
        tenancy: DBModel = self._repository.fetch(tenancy=name)
        if tenancy is None:
            raise NotFoundException(f"not_found: {name}")
        tenancy.is_enabled = False
        self._repository.upsert(tenancy=tenancy)

    def enable(self, name: str) -> None:
        tenancy: DBModel = self._repository.fetch(tenancy=name, is_enabled=False)
        if tenancy is None:
            raise NotFoundException(f"not_found: {name}")
        tenancy.is_enabled = True
        self._repository.upsert(tenancy=tenancy)
