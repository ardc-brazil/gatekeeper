import hashlib
import hmac
import logging

import bcrypt

HMAC_PREFIX = "hmac-sha256$"

MIN_PEPPER_LENGTH = 16

# Do not hand bcrypt a value of another shape: a truncated one panics inside its
# Rust extension, past `except Exception`.
BCRYPT_LENGTH = 60


def is_bcrypt_hash(stored: str) -> bool:
    return len(stored) == BCRYPT_LENGTH and stored.startswith("$2")


def verify_bcrypt(password: bytes, stored: str) -> bool:
    if not is_bcrypt_hash(stored):
        return False
    try:
        return bcrypt.checkpw(password, stored.encode("utf-8"))
    except ValueError:
        return False


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password=password.encode("utf-8"), salt=salt)
    return hashed_password.decode("utf-8")


def check_password(password: str, hashed_password: str) -> bool:
    return verify_bcrypt(password.encode("utf-8"), hashed_password)


def hash_secret(secret: str, pepper: str) -> str:
    if len(pepper) < MIN_PEPPER_LENGTH:
        raise ValueError(
            f"the client secret pepper must be at least {MIN_PEPPER_LENGTH} characters"
        )
    digest = hmac.new(
        key=pepper.encode("utf-8"),
        msg=secret.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"{HMAC_PREFIX}{digest}"


def is_legacy_hash(stored: str) -> bool:
    return not stored.startswith(HMAC_PREFIX)


def verify_secret(secret: str, stored: str, pepper: str) -> bool:
    if is_legacy_hash(stored):
        if not is_bcrypt_hash(stored):
            logging.warning("stored client secret is not in a readable format")
            return False
        return check_password(password=secret, hashed_password=stored)
    return hmac.compare_digest(stored, hash_secret(secret, pepper))
