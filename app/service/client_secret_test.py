import time

import pytest

from app.service.secret import (
    hash_password,
    hash_secret,
    is_legacy_hash,
    verify_secret,
)

PEPPER = "a-server-side-pepper-long-enough-to-matter"


def test_a_secret_verifies_against_its_own_hash():
    stored = hash_secret("g-aZkbWom3deiAX-vtoT", PEPPER)

    assert verify_secret("g-aZkbWom3deiAX-vtoT", stored, PEPPER) is True


def test_a_different_secret_does_not_verify():
    stored = hash_secret("the-real-secret", PEPPER)

    assert verify_secret("another-secret", stored, PEPPER) is False


def test_the_algorithm_is_named_in_the_stored_value():
    assert hash_secret("x", PEPPER).startswith("hmac-sha256$")


def test_the_secret_itself_never_appears_in_the_stored_value():
    assert "the-real-secret" not in hash_secret("the-real-secret", PEPPER)


def test_a_hash_made_with_another_pepper_does_not_verify():
    stored = hash_secret("the-real-secret", "one-pepper-long-enough")

    assert verify_secret("the-real-secret", stored, "other-pepper-long-enough") is False


def test_the_same_secret_and_pepper_always_give_the_same_hash():
    assert hash_secret("x", PEPPER) == hash_secret("x", PEPPER)


def test_a_bcrypt_hash_from_before_this_change_still_verifies():
    legacy = hash_password("the-real-secret")

    assert verify_secret("the-real-secret", legacy, PEPPER) is True
    assert verify_secret("wrong", legacy, PEPPER) is False


def test_a_bcrypt_hash_is_reported_as_needing_an_upgrade():
    assert is_legacy_hash(hash_password("x")) is True
    assert is_legacy_hash(hash_secret("x", PEPPER)) is False


def test_an_empty_pepper_is_refused_rather_than_silently_weakening_the_hash():
    with pytest.raises(ValueError):
        hash_secret("x", "")


@pytest.mark.parametrize(
    "stored",
    [
        "",
        "not-a-hash",
        "sha512$deadbeef",
        "$2b$12$too-short",
        "$2b$12$" + "x" * 60,
        "hmac-sha256",
    ],
)
def test_a_stored_value_that_cannot_be_read_is_a_failed_verification(stored: str):
    assert verify_secret("the-real-secret", stored, PEPPER) is False


def test_a_legacy_hash_with_an_invalid_salt_fails_rather_than_raising():
    stored = "$2b$10$" + "x" * 53

    assert verify_secret("the-real-secret", stored, PEPPER) is False


def test_verification_is_fast_enough_not_to_block_the_event_loop():
    stored = hash_secret("the-real-secret", PEPPER)

    start = time.perf_counter()
    for _ in range(100):
        verify_secret("the-real-secret", stored, PEPPER)
    per_call_ms = (time.perf_counter() - start) * 1000 / 100

    assert per_call_ms < 1, f"{per_call_ms:.3f}ms per verification"
