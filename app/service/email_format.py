from datetime import date, datetime


def long_date(value: datetime | date) -> str:
    return f"{value:%B} {value.day}, {value.year}"


def short_date(value: datetime | date) -> str:
    return f"{value:%B} {value.day}"


def tenancy_display_name(tenancy: str | None) -> str:
    if not tenancy:
        return "the workspace"
    return (
        tenancy.rstrip("/")
        .rsplit("/", 1)[-1]
        .replace("-", " ")
        .replace("_", " ")
        .title()
    )


def first_name(name: str) -> str:
    parts = (name or "").split()
    return parts[0] if parts else ""
