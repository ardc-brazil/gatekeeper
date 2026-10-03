import hashlib
import hmac
import secrets
from uuid import UUID

from app.service.secret import MIN_PEPPER_LENGTH

CODE_LENGTH = 6
CODE_SPACE = 10**CODE_LENGTH


def new_code() -> str:
    return f"{secrets.randbelow(CODE_SPACE):0{CODE_LENGTH}d}"


def code_hash(pepper: str, challenge_id: UUID, code: str) -> str:
    if len(pepper) < MIN_PEPPER_LENGTH:
        raise ValueError(
            f"the challenge pepper must be at least {MIN_PEPPER_LENGTH} characters"
        )
    message = f"{challenge_id}{code}".encode("utf-8")
    return hmac.new(pepper.encode("utf-8"), message, hashlib.sha256).hexdigest()
