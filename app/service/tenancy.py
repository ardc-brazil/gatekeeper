import logging
from typing import List
from app.model.db.tenancy import Tenancy as DBModel
from app.model.tenancy import Tenancy
from app.repository.tenancy import TenancyRepository
from exception.NotFoundException import NotFoundException


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
        try:
            res: DBModel = self._repository.fetch(name, is_enabled)
            if res is None:
                return None
            tenancy: Tenancy = self.__adapt_tenancy(res)
            return tenancy
        except Exception as e:
            logging.error(e)
            raise e

    def fetch_all(self, is_enabled: bool = True) -> List[Tenancy]:
        try:
            res: DBModel = self._repository.fetch_all(is_enabled)
            if res is None:
                return []
            tenancies: List[Tenancy] = [self.__adapt_tenancy(tenancy) for tenancy in res]
            return tenancies
        except Exception as e:
            logging.error(e)
            raise e

    def create(self, tenancy: Tenancy) -> None:
        try:
            tenancy = DBModel(name=tenancy.name, is_enabled=tenancy.is_enabled)
            self._repository.upsert(tenancy)
        except Exception as e:
            logging.error(e)
            raise e

    def update(self, old_name: str, updated_tenancy: Tenancy) -> None:
        old_tenancy: DBModel = self._repository.fetch(old_name)
        if old_tenancy is None: 
            raise NotFoundException(f"not_found: {old_name}")
        
        old_tenancy.name = updated_tenancy.name
        old_tenancy.is_enabled = updated_tenancy.is_enabled
        self._repository.upsert(old_tenancy)

    def disable(self, name: str) -> None:
        try:
            tenancy: DBModel = self._repository.fetch(name)
            if tenancy is None:
                raise NotFoundException(f"not_found: {name}")
            tenancy.is_enabled = False
            self._repository.upsert(tenancy)
        except Exception as e:
            logging.error(e)
            raise e

    def enable(self, name: str) -> None:
        try:
            tenancy: DBModel = self._repository.fetch(name, False)
            if tenancy is None:
                raise NotFoundException(f"not_found: {name}")
            tenancy.is_enabled = True
            self._repository.upsert(tenancy)
        except Exception as e:
            logging.error(e)
            raise e
