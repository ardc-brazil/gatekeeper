import base64
import hashlib
import hmac
import secrets

import bcrypt

from app.service.secret import BCRYPT_LENGTH, MIN_PEPPER_LENGTH

BCRYPT_ROUNDS = 10
MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128


def password_is_acceptable(password: str) -> bool:
    return MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH


def _is_bcrypt_hash(stored: str) -> bool:
    return len(stored) == BCRYPT_LENGTH and stored.startswith("$2")


class PasswordHasher:
    def __init__(self, pepper: str, rounds: int = BCRYPT_ROUNDS) -> None:
        if len(pepper) < MIN_PEPPER_LENGTH:
            raise ValueError(
                f"the password pepper must be at least {MIN_PEPPER_LENGTH} characters"
            )
        self._pepper = pepper.encode("utf-8")
        self._rounds = rounds
        self._dummy = self.hash(secrets.token_urlsafe(32))

    def hash(self, password: str) -> str:
        salt = bcrypt.gensalt(rounds=self._rounds)
        return bcrypt.hashpw(self._peppered(password), salt).decode("utf-8")

    def verify(self, password: str, stored: str) -> bool:
        # A value of another shape can panic inside bcrypt's Rust extension.
        if not _is_bcrypt_hash(stored):
            return False
        return bcrypt.checkpw(self._peppered(password), stored.encode("utf-8"))

    def burn(self, password: str) -> None:
        self.verify(password, self._dummy)

    def _peppered(self, password: str) -> bytes:
        digest = hmac.new(
            self._pepper, password.encode("utf-8"), hashlib.sha256
        ).digest()
        return base64.b64encode(digest)
