from typing import List
from app.model.db.tenancy import Tenancy as DBModel
from app.model.tenancy import Tenancy
from app.repository.tenancy import TenancyRepository
from app.exception.not_found import NotFoundException


class TenancyService:
    def __init__(self, repository: TenancyRepository) -> None:
        self._repository: TenancyRepository = repository

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
        tenancy = DBModel(name=tenancy.name, is_enabled=tenancy.is_enabled)
        self._repository.upsert(tenancy)

    def update(self, old_name: str, updated_tenancy: Tenancy) -> None:
        old_tenancy: DBModel = self._repository.fetch(tenancy=old_name)
        if old_tenancy is None:
            raise NotFoundException(f"not_found: {old_name}")

        old_tenancy.name = updated_tenancy.name
        old_tenancy.is_enabled = updated_tenancy.is_enabled
        self._repository.upsert(tenancy=old_tenancy)

    def disable(self, name: str) -> None:
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
