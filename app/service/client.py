from typing import List
from uuid import UUID
from app.exception.not_found import NotFoundException
from app.model.db.client import Client as DBModel
from app.model.client import Client
from app.repository.client import ClientRepository
from app.service.secret import hash_secret


class ClientService:
    def __init__(self, repository: ClientRepository, client_secret_pepper: str) -> None:
        self._repository: ClientRepository = repository
        self._client_secret_pepper = client_secret_pepper

    def __adapt_client(self, client: DBModel) -> Client:
        return Client(
            key=client.key,
            name=client.name,
            is_enabled=client.is_enabled,
            secret=client.secret,
        )

    # Deliberately not cached. There are two instances, and an lru_cache here
    # meant a rotated secret or a disabled client kept working on whichever one
    # did not serve the change until it restarted. Verification no longer costs
    # 150ms, so the lookup is the only cost left and it is under a millisecond.
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
            secret=hash_secret(secret, self._client_secret_pepper),
            is_enabled=True,
        )

        return self._repository.upsert(client=model).key

    def update(
        self, key: UUID, name: str | None = None, secret: str | None = None
    ) -> None:
        client: DBModel = self._repository.fetch(api_key=key)
        if client is None:
            raise NotFoundException(f"not_found: {key}")

        if name is not None:
            client.name = name
        if secret is not None:
            client.secret = hash_secret(secret, self._client_secret_pepper)

        self._repository.upsert(client=client)

    def replace_secret_hash(self, key: UUID, secret_hash: str) -> None:
        client: DBModel = self._repository.fetch(api_key=key)
        if client is None:
            return
        client.secret = secret_hash
        self._repository.upsert(client=client)

    def disable(self, key: UUID) -> None:
        client: DBModel = self._repository.fetch(api_key=key)
        if client is None:
            raise NotFoundException(f"not_found: {key}")
        client.is_enabled = False
        self._repository.upsert(client=client)

    def enable(self, key: UUID) -> None:
        client: DBModel = self._repository.fetch(api_key=key, is_enabled=False)
        if client is None:
            raise NotFoundException(f"not_found: {key}")
        client.is_enabled = True
        self._repository.upsert(client=client)
