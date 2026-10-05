from datetime import date, datetime

from app.model.tenancy import derived_display_name


def long_date(value: datetime | date) -> str:
    return f"{value:%B} {value.day}, {value.year}"


def short_date(value: datetime | date) -> str:
    return f"{value:%B} {value.day}"


def tenancy_display_name(tenancy: str | None) -> str:
    if not tenancy:
        return "the workspace"
    return derived_display_name(tenancy)


def first_name(name: str) -> str:
    parts = (name or "").split()
    return parts[0] if parts else ""
