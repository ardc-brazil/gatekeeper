from typing import Any

REDACTED = "[redacted]"

SAFE_METADATA_KEYS = frozenset(
    {
        "description",
        "tags",
        "level",
        "realm",
        "source",
        "license",
        "category",
        "database",
        "start_date",
        "end_date",
        "creation_date",
        "location",
        "data_type",
        "grid_type",
        "variables",
        "resolution",
        "source_instrument",
        "additional_information",
        "is_enabled",
    }
)


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        return REDACTED
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact(item) for key, item in value.items()}
    return value


def redact_metadata(data: dict | None) -> dict:
    if not data:
        return {}
    return {
        key: value if key in SAFE_METADATA_KEYS else _redact(value)
        for key, value in data.items()
    }
