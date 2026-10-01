from dataclasses import dataclass
from datetime import datetime, timedelta

MAX_EMBARGO_PERIOD = timedelta(days=90)
REMINDER_OFFSETS_DAYS = (15, 10, 5, 1)


def embargo_active(until: datetime | None, now: datetime) -> bool:
    return until is not None and until > now


@dataclass
class Embargo:
    until: datetime
    active: bool
    metadata_visible: bool
    note: str | None = None
