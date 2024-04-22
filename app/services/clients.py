from functools import lru_cache
import logging
from app.models.clients import Clients
from app.repositories.clients import ClientsRepository
from app.services.secrets import hash_password
from werkzeug.exceptions import NotFound

repository = ClientsRepository()


class ClientsService:
    def __adapt_client(self, client):
        return {
            "name": client.name,
            "key": client.key,
            "is_enabled": client.is_enabled,
            "secret": client.secret,
        }

    @lru_cache
    def fetch(self, api_key):
        try:
            res = repository.fetch(api_key)
            if res is not None:
                client = self.__adapt_client(res)
                return client

            return None
        except Exception as e:
            logging.error(e)
            raise e

    def fetch_all(self):
        try:
            res = repository.fetch_all()
            if res is not None:
                clients = [self.__adapt_client(client) for client in res]
                return clients

            return []
        except Exception as e:
            logging.error(e)
            raise e

    def create(self, request_body):
        try:
            client = Clients(
                name=request_body["name"],
                secret=hash_password(request_body["secret"]),
                is_enabled=True,
            )
            created_key = repository.upsert(client).key
            self.fetch.cache_clear()
            return created_key
        except Exception as e:
            logging.error(e)
            raise e

    def update(self, key, request_body):
        try:
            client = repository.fetch(key)
            if client is None:
                raise NotFound()

            client.name = request_body["name"]
            client.secret = hash_password(request_body["secret"])
            repository.upsert(client)
            self.fetch.cache_clear()
        except Exception as e:
            logging.error(e)
            raise e

    def disable(self, key):
        try:
            client = repository.fetch(key)
            if client is None:
                raise NotFound()
            client.is_enabled = False
            repository.upsert(client)
            self.fetch.cache_clear()
        except Exception as e:
            logging.error(e)
            raise e

    def enable(self, key):
        try:
            client = repository.fetch(key, False)
            if client is None:
                raise NotFound()
            client.is_enabled = True
            repository.upsert(client)
            self.fetch.cache_clear()
        except Exception as e:
            logging.error(e)
            raise e
