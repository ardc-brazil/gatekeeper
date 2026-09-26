import hashlib
import hmac

import bcrypt

# An API secret is a random, system-generated value, not a human password.
# bcrypt's cost exists to make brute force against low-entropy passwords
# expensive; against 120 bits of randomness it defends nothing and costs 150ms
# of blocked event loop per request. The pepper is what keeps a leaked database
# useless on its own: it lives in the environment, not in the table.
HMAC_PREFIX = "hmac-sha256$"

MIN_PEPPER_LENGTH = 16


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password=password.encode("utf-8"), salt=salt)
    return hashed_password.decode("utf-8")


def check_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        password=password.encode("utf-8"),
        hashed_password=hashed_password.encode("utf-8"),
    )


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
        return check_password(password=secret, hashed_password=stored)
    return hmac.compare_digest(stored, hash_secret(secret, pepper))
