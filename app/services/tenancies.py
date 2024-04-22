import logging
from app.models.tenancies import Tenancies
from app.repositories.tenancies import TenancyRepository
from werkzeug.exceptions import NotFound

repository = TenancyRepository()


class TenancyService:
    def __adapt_tenancy(self, tenancy):
        return {
            "name": tenancy.name,
            "is_enabled": tenancy.is_enabled,
            "created_at": tenancy.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": tenancy.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        }

    def fetch(self, name, is_enabled=True):
        try:
            res = repository.fetch(name, is_enabled)
            if res is not None:
                tenancy = self.__adapt_tenancy(res)
                return tenancy

            return None
        except Exception as e:
            logging.error(e)
            raise e

    def fetch_all(self, is_enabled=True):
        try:
            res = repository.fetch_all(is_enabled)
            if res is not None:
                tenancies = [self.__adapt_tenancy(tenancy) for tenancy in res]
                return tenancies

            return []
        except Exception as e:
            logging.error(e)
            raise e

    def create(self, request_body):
        try:
            tenancy = Tenancies(name=request_body["name"], is_enabled=True)
            repository.upsert(tenancy)
        except Exception as e:
            logging.error(e)
            raise e

    def update(self, old_name, request_body):
        try:
            tenancy = repository.fetch(old_name)
            if tenancy is None:
                raise NotFound()

            tenancy.name = request_body["name"]
            tenancy.is_enabled = request_body["is_enabled"]
            repository.upsert(tenancy)
        except Exception as e:
            logging.error(e)
            raise e

    def disable(self, name):
        try:
            tenancy = repository.fetch(name)
            if tenancy is None:
                raise NotFound()
            tenancy.is_enabled = False
            repository.upsert(tenancy)
        except Exception as e:
            logging.error(e)
            raise e

    def enable(self, name):
        try:
            tenancy = repository.fetch(name, False)
            if tenancy is None:
                raise NotFound()
            tenancy.is_enabled = True
            repository.upsert(tenancy)
        except Exception as e:
            logging.error(e)
            raise e
