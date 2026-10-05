from sqlalchemy.exc import IntegrityError

from app.exception.conflict import ConflictException


def violates(error: IntegrityError, constraint: str) -> bool:
    diag = getattr(error.orig, "diag", None)
    return getattr(diag, "constraint_name", None) == constraint


def raise_conflict(error: IntegrityError, codes: dict[str, str]) -> None:
    for constraint, code in codes.items():
        if violates(error, constraint):
            raise ConflictException(code) from error
