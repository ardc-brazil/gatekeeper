import unittest
from unittest.mock import Mock, patch
from uuid import uuid4
from app.model.db.client import Client as DBModel
from app.repository.client import ClientRepository
from app.exception.not_found import NotFoundException
from app.service.client import ClientService


class TestClientService(unittest.TestCase):
    def setUp(self):
        self.repository = Mock(spec=ClientRepository)
        self.client_service = ClientService(self.repository)

    def test_fetch_success(self):
        api_key = uuid4()
        db_client = DBModel(
            key=api_key, name="client1", is_enabled=True, secret="secret"
        )
        self.repository.fetch.return_value = db_client

        client = self.client_service.fetch(api_key)
        self.assertIsNotNone(client)
        self.assertEqual(client.key, api_key)

    def test_fetch_not_found(self):
        self.repository.fetch.return_value = None
        client = self.client_service.fetch(uuid4())
        self.assertIsNone(client)

    def test_fetch_all_success(self):
        db_clients = [
            DBModel(key=uuid4(), name="client1", is_enabled=True, secret="secret"),
            DBModel(key=uuid4(), name="client2", is_enabled=True, secret="secret"),
        ]
        self.repository.fetch_all.return_value = db_clients

        clients = self.client_service.fetch_all()
        self.assertEqual(len(clients), 2)
        self.assertEqual(clients[0].name, "client1")
        self.assertEqual(clients[1].name, "client2")

    def test_fetch_all_empty(self):
        self.repository.fetch_all.return_value = []
        clients = self.client_service.fetch_all()
        self.assertEqual(len(clients), 0)

    def test_create(self):
        name = "new_client"
        secret = "secret"
        created_key = uuid4()
        db_client = DBModel(
            key=created_key, name=name, is_enabled=True, secret="hashed_secret"
        )
        self.repository.upsert.return_value = db_client

        with patch("app.service.client.hash_password") as mock_hash_password:
            mock_hash_password.return_value = "hashed_secret"
            returned_key = self.client_service.create(name, secret)

        self.repository.upsert.assert_called_once()
        called_arg = self.repository.upsert.call_args[1]["client"]
        self.assertEqual(called_arg.name, name)
        self.assertEqual(called_arg.secret, "hashed_secret")
        self.assertTrue(called_arg.is_enabled)
        self.assertEqual(called_arg.key, None)

        self.assertEqual(returned_key, created_key)

    def test_update_success(self):
        key = uuid4()
        db_client = DBModel(
            key=key, name="old_client", is_enabled=True, secret="old_secret"
        )
        self.repository.fetch.return_value = db_client

        with patch("app.service.client.hash_password") as mock_hash_password:
            mock_hash_password.return_value = "hashed_secret"
            self.client_service.update(key, name="updated_client", secret="new_secret")

        self.repository.upsert.assert_called_once()
        self.assertEqual(db_client.name, "updated_client")
        self.assertEqual(db_client.secret, "hashed_secret")

    def test_update_not_found(self):
        self.repository.fetch.return_value = None
        with self.assertRaises(NotFoundException):
            self.client_service.update(
                uuid4(), name="updated_client", secret="new_secret"
            )

    def test_disable_success(self):
        key = uuid4()
        db_client = DBModel(key=key, name="client1", is_enabled=True, secret="secret")
        self.repository.fetch.return_value = db_client

        self.client_service.disable(key)
        self.repository.upsert.assert_called_once()
        self.assertFalse(db_client.is_enabled)

    def test_disable_not_found(self):
        self.repository.fetch.return_value = None
        with self.assertRaises(NotFoundException):
            self.client_service.disable(uuid4())

    def test_enable_success(self):
        key = uuid4()
        db_client = DBModel(key=key, name="client1", is_enabled=False, secret="secret")
        self.repository.fetch.return_value = db_client

        self.client_service.enable(key)
        self.repository.upsert.assert_called_once()
        self.assertTrue(db_client.is_enabled)

    def test_enable_not_found(self):
        self.repository.fetch.return_value = None
        with self.assertRaises(NotFoundException):
            self.client_service.enable(uuid4())

    def test_cache_behavior(self):
        api_key = uuid4()
        db_client = DBModel(
            key=api_key, name="client1", is_enabled=True, secret="secret"
        )
        self.repository.fetch.return_value = db_client

        self.assertEqual(self.client_service.fetch(api_key).name, "client1")
        self.repository.fetch.assert_called_once_with(api_key=api_key)

        self.assertEqual(self.client_service.fetch(api_key).name, "client1")
        self.repository.fetch.assert_called_once_with(api_key=api_key)

        updated_name = "updated_client"
        db_client.name = updated_name
        self.client_service.update(api_key, name=updated_name)

        self.assertEqual(self.client_service.fetch(api_key).name, updated_name)

    def test_the_cache_is_shared_across_requests(self):
        # The service used to be a Factory, so every request built a new instance
        # and the cache — keyed on `self` — never hit. Asserting through the
        # container is the only way to catch that; reusing one instance by hand
        # passes either way.
        from app.container import Container

        container = Container()

        self.assertIs(container.client_service(), container.client_service())


if __name__ == "__main__":
    unittest.main()
