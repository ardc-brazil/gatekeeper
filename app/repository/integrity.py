from sqlalchemy.exc import IntegrityError


def violates(error: IntegrityError, constraint: str) -> bool:
    diag = getattr(error.orig, "diag", None)
    return getattr(diag, "constraint_name", None) == constraint
