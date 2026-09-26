from unittest.mock import Mock
from uuid import uuid4

from app.model.db.client import Client as DBModel
from app.service.client import ClientService
from app.service.secret import HMAC_PREFIX

PEPPER = "a-server-side-pepper-long-enough"


def _service():
    repository = Mock()
    return ClientService(repository=repository, client_secret_pepper=PEPPER), repository


def _row(key, secret="stored", is_enabled=True):
    return DBModel(key=key, name="a client", secret=secret, is_enabled=is_enabled)


def test_a_disabled_client_is_not_served_from_a_stale_cache():
    service, repository = _service()
    key = uuid4()
    repository.fetch.return_value = _row(key)

    assert service.fetch(key) is not None

    repository.fetch.return_value = None

    assert service.fetch(key) is None


def test_a_rotated_secret_is_visible_on_the_next_fetch():
    service, repository = _service()
    key = uuid4()
    repository.fetch.return_value = _row(key, secret="old-hash")

    assert service.fetch(key).secret == "old-hash"

    repository.fetch.return_value = _row(key, secret="new-hash")

    assert service.fetch(key).secret == "new-hash"


def test_a_created_client_is_stored_in_the_new_format():
    service, repository = _service()
    repository.upsert.return_value = _row(uuid4())

    service.create(name="a client", secret="the-secret")

    stored = repository.upsert.call_args.kwargs["client"].secret
    assert stored.startswith(HMAC_PREFIX)


def test_an_updated_secret_is_stored_in_the_new_format():
    service, repository = _service()
    key = uuid4()
    repository.fetch.return_value = _row(key, secret="old-hash")

    service.update(key=key, secret="the-new-secret")

    stored = repository.upsert.call_args.kwargs["client"].secret
    assert stored.startswith(HMAC_PREFIX)


def test_replace_secret_hash_writes_exactly_what_it_is_given():
    service, repository = _service()
    key = uuid4()
    repository.fetch.return_value = _row(key, secret="old-bcrypt-hash")

    service.replace_secret_hash(key=key, secret_hash="hmac-sha256$abc")

    assert repository.upsert.call_args.kwargs["client"].secret == "hmac-sha256$abc"


def test_replace_secret_hash_on_an_unknown_client_does_not_write():
    service, repository = _service()
    repository.fetch.return_value = None

    service.replace_secret_hash(key=uuid4(), secret_hash="hmac-sha256$abc")

    repository.upsert.assert_not_called()
