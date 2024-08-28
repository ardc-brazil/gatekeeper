from functools import lru_cache
from typing import List
from uuid import UUID
from app.exception.not_found import NotFoundException
from app.model.db.client import Client as DBModel
from app.model.client import Client
from app.repository.client import ClientRepository
from app.service.secret import hash_password


class ClientService:
    def __init__(self, repository: ClientRepository) -> None:
        self._repository: ClientRepository = repository

    def __adapt_client(self, client: DBModel) -> Client:
        return Client(
            key=client.key,
            name=client.name,
            is_enabled=client.is_enabled,
            secret=client.secret,
        )

    @lru_cache
    def fetch(self, api_key: UUID) -> Client | None:
        res: DBModel = self._repository.fetch(api_key=api_key)
        if res is None:
            return None
        client: Client = self.__adapt_client(client=res)
        return client

    def fetch_all(self) -> List[Client]:
        res: DBModel = self._repository.fetch_all()
        if res is None:
            return []

        return [self.__adapt_client(client=client) for client in res]

    def create(self, name: str, secret: str) -> UUID:
        model = DBModel(
            name=name,
            secret=hash_password(password=secret),
            is_enabled=True,
        )
        
        created_key = self._repository.upsert(client=model).key
        self.fetch.cache_clear()
        return created_key

    def update(
        self, key: UUID, name: str | None = None, secret: str | None = None
    ) -> None:
        client: DBModel = self._repository.fetch(api_key=key)
        if client is None:
            raise NotFoundException(f"not_found: {key}")

        if name is not None:
            client.name = name
        if secret is not None:
            client.secret = hash_password(password=secret)

        self._repository.upsert(client=client)
        self.fetch.cache_clear()

    def disable(self, key: UUID) -> None:
        client: DBModel = self._repository.fetch(api_key=key)
        if client is None:
            raise NotFoundException(f"not_found: {key}")
        client.is_enabled = False
        self._repository.upsert(client=client)
        self.fetch.cache_clear()

    def enable(self, key: UUID) -> None:
        client: DBModel = self._repository.fetch(api_key=key, is_enabled=False)
        if client is None:
            raise NotFoundException(f"not_found: {key}")
        client.is_enabled = True
        self._repository.upsert(client=client)
        self.fetch.cache_clear()
