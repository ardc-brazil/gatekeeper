import logging
import re
import sys
from contextvars import ContextVar
from typing import Any, TextIO

from pythonjsonlogger import jsonlogger

from app.config import settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="")

REDACTED = "[redacted]"

_SECRET_WORDS = r"token|secret|password|authorization|api[-_]?key"

_STANDARD_RECORD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__
) | {"message", "asctime", "taskName"}


def fields(**values: Any) -> dict[str, Any]:
    """Extras for a log record, renaming any key that LogRecord already uses."""
    return {
        f"log_{key}" if key in _STANDARD_RECORD_ATTRS else key: value
        for key, value in values.items()
    }


class Redactor:
    KEY_PATTERN = re.compile(_SECRET_WORDS, re.IGNORECASE)

    # Matches a credential already interpolated into a message, which no
    # key-based check can reach.
    VALUE_PATTERN = re.compile(
        r"(['\"]?[\w\-]*(?:" + _SECRET_WORDS + r")[\w\-]*['\"]?\s*[:=]\s*\[?\s*['\"]?)"
        r"([^'\",\}\]\s]+)",
        re.IGNORECASE,
    )

    @classmethod
    def scrub(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: REDACTED if cls.KEY_PATTERN.search(str(key)) else cls.scrub(inner)
                for key, inner in value.items()
            }
        if isinstance(value, (list, tuple)):
            return type(value)(cls.scrub(item) for item in value)
        if isinstance(value, str):
            return cls.scrub_text(value)
        return value

    @classmethod
    def scrub_text(cls, text: str) -> str:
        return cls.VALUE_PATTERN.sub(r"\1" + REDACTED, text)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = Redactor.scrub(record.msg)
        if record.args:
            record.args = Redactor.scrub(record.args)
        for key, value in list(record.__dict__.items()):
            if key in _STANDARD_RECORD_ATTRS:
                continue
            record.__dict__[key] = (
                REDACTED if Redactor.KEY_PATTERN.search(key) else Redactor.scrub(value)
            )
        return True


class JsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record["timestamp"] = self.formatTime(record)
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        request_id = request_id_var.get()
        if request_id:
            log_record["request_id"] = request_id
        log_record.pop("taskName", None)
        # uvicorn attaches an ANSI-coloured copy of its own message.
        log_record.pop("color_message", None)


def _module_levels() -> dict[str, int | str]:
    return {
        "uvicorn": settings.LOG_LEVEL,
        # Replaced by the `http.access` line the middleware emits.
        "uvicorn.access": logging.WARNING,
        "uvicorn.error": settings.LOG_LEVEL,
        "tests": logging.INFO,
        "casbin.enforcer": settings.CASBIN_LOG_LEVEL,
        "casbin.policy": settings.CASBIN_LOG_LEVEL,
        "casbin.role": settings.CASBIN_LOG_LEVEL,
        "sqlalchemy.engine": settings.SQLALCHEMY_LOG_LEVEL,
    }


def setup_logging(stream: TextIO = None) -> None:
    handler = logging.StreamHandler(stream if stream is not None else sys.stdout)
    handler.setFormatter(JsonFormatter("%(message)s"))
    handler.addFilter(RedactingFilter())

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(settings.LOG_LEVEL)

    # Levels only: a handler here emits every line a second time.
    for name, level in _module_levels().items():
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.handlers.clear()
        logger.propagate = True
