from typing import Any, Iterable

MASK = "[masked]"


def _replace(value: Any, secrets: list[str]) -> Any:
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, MASK)
        return value
    if isinstance(value, list):
        return [_replace(item, secrets) for item in value]
    if isinstance(value, dict):
        return {key: _replace(item, secrets) for key, item in value.items()}
    return value


def mask_secrets(
    context: dict, body_text: str, secret_fields: Iterable[str]
) -> tuple[dict, str]:
    names = set(secret_fields)
    secrets = [
        context[name]
        for name in names
        if isinstance(context.get(name), str) and context[name]
    ]
    masked = {
        key: MASK if key in names else _replace(value, secrets)
        for key, value in context.items()
    }
    for secret in secrets:
        body_text = body_text.replace(secret, MASK)
    return masked, body_text
