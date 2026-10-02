import re

from app.exception.bad_request import BadRequestException, ErrorDetails

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ORCID = re.compile(r"^(\d{4})-?(\d{4})-?(\d{4})-?(\d{3}[\dX])$")
_ORCID_PREFIXES = ("https://orcid.org/", "http://orcid.org/", "orcid.org/")


def normalise_email(value: str) -> str:
    email = (value or "").strip().lower()
    if not _EMAIL.match(email):
        raise BadRequestException(errors=[ErrorDetails(code="invalid_email")])
    return email


def orcid_checksum_ok(value: str) -> bool:
    digits = value.replace("-", "")
    total = 0
    for char in digits[:15]:
        total = (total + int(char)) * 2
    result = (12 - total % 11) % 11
    return digits[15] == ("X" if result == 10 else str(result))


def normalise_orcid(value: str) -> str:
    orcid = (value or "").strip()
    for prefix in _ORCID_PREFIXES:
        if orcid.lower().startswith(prefix):
            orcid = orcid[len(prefix) :]
            break
    match = _ORCID.match(orcid.upper())
    if match is None:
        raise BadRequestException(errors=[ErrorDetails(code="invalid_orcid")])
    orcid = "-".join(match.groups())
    if not orcid_checksum_ok(orcid):
        raise BadRequestException(errors=[ErrorDetails(code="invalid_orcid")])
    return orcid
