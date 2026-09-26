import logging
from unittest.mock import Mock

import pytest

from app.exception.unauthorized import UnauthorizedException
from app.service.auth import AuthService
from app.service.secret import hash_password, hash_secret

PEPPER = "a-server-side-pepper-long-enough"
SECRET = "g-aZkbWom3deiAX-vtoT"


@pytest.fixture
def client_service():
    return Mock()


@pytest.fixture
def auth_service(client_service):
    return AuthService(
        client_service=client_service,
        casbin_enforcer=Mock(),
        file_upload_token_secret="irrelevant-here",
        client_secret_pepper=PEPPER,
    )


def _client(secret: str):
    return Mock(secret=secret, key="a-key")


def test_accepts_a_secret_stored_in_the_new_format(auth_service, client_service):
    client_service.fetch.return_value = _client(hash_secret(SECRET, PEPPER))

    assert auth_service.authorize_client("a-key", SECRET) is None


def test_rejects_a_wrong_secret(auth_service, client_service):
    client_service.fetch.return_value = _client(hash_secret(SECRET, PEPPER))

    with pytest.raises(UnauthorizedException):
        auth_service.authorize_client("a-key", "not-the-secret")


def test_accepts_a_secret_still_stored_as_bcrypt(auth_service, client_service):
    client_service.fetch.return_value = _client(hash_password(SECRET))

    assert auth_service.authorize_client("a-key", SECRET) is None


def test_upgrades_a_bcrypt_hash_once_it_has_been_verified(auth_service, client_service):
    client_service.fetch.return_value = _client(hash_password(SECRET))

    auth_service.authorize_client("a-key", SECRET)

    client_service.replace_secret_hash.assert_called_once_with(
        key="a-key", secret_hash=hash_secret(SECRET, PEPPER)
    )


def test_does_not_upgrade_a_hash_that_is_already_in_the_new_format(
    auth_service, client_service
):
    client_service.fetch.return_value = _client(hash_secret(SECRET, PEPPER))

    auth_service.authorize_client("a-key", SECRET)

    client_service.replace_secret_hash.assert_not_called()


def test_does_not_upgrade_after_a_failed_verification(auth_service, client_service):
    client_service.fetch.return_value = _client(hash_password(SECRET))

    with pytest.raises(UnauthorizedException):
        auth_service.authorize_client("a-key", "not-the-secret")

    client_service.replace_secret_hash.assert_not_called()


def test_a_failed_upgrade_does_not_fail_the_request(auth_service, client_service):
    client_service.fetch.return_value = _client(hash_password(SECRET))
    client_service.replace_secret_hash.side_effect = RuntimeError("database is down")

    assert auth_service.authorize_client("a-key", SECRET) is None


def test_never_logs_the_secret_that_was_sent(auth_service, client_service, caplog):
    client_service.fetch.return_value = _client(hash_secret(SECRET, PEPPER))

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(UnauthorizedException):
            auth_service.authorize_client("a-key", "a-secret-that-must-not-be-logged")

    assert "a-secret-that-must-not-be-logged" not in caplog.text


def test_never_logs_the_api_key_of_an_unknown_client(
    auth_service, client_service, caplog
):
    client_service.fetch.return_value = None

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(UnauthorizedException):
            auth_service.authorize_client("5060b1a2-a-key-that-must-not-be-logged", "x")

    assert "5060b1a2-a-key-that-must-not-be-logged" not in caplog.text
