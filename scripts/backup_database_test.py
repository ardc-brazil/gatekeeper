from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.backup_database import (
    MARKER,
    backup_name,
    parse_backup_date,
    storage_is_mounted,
    to_prune,
)

NOW = datetime(2026, 9, 26, 23, 30, 0, tzinfo=timezone.utc)


def test_a_backup_is_named_after_the_instant_it_was_taken():
    assert backup_name(NOW) == "gatekeeper_db-20260926T233000Z.dump"


def test_a_name_round_trips_back_to_its_date():
    assert parse_backup_date(backup_name(NOW)) == NOW


def test_a_file_that_is_not_a_backup_has_no_date():
    assert parse_backup_date("notes.txt") is None
    assert parse_backup_date("gatekeeper_db-nonsense.dump") is None


def _names(*dates: str) -> list[str]:
    return [f"gatekeeper_db-{d}.dump" for d in dates]


def test_keeps_everything_inside_the_daily_window():
    names = _names("20260926T233000Z", "20260920T010000Z", "20260828T010000Z")

    assert to_prune(names, NOW, keep_daily=30, keep_monthly=12) == []


def test_prunes_a_daily_backup_once_it_leaves_the_window():
    names = _names("20260926T233000Z", "20260810T010000Z")

    assert to_prune(names, NOW, keep_daily=30, keep_monthly=12) == [
        "gatekeeper_db-20260810T010000Z.dump"
    ]


def test_keeps_the_first_of_the_month_beyond_the_daily_window():
    names = _names("20260801T010000Z", "20260810T010000Z")

    assert to_prune(names, NOW, keep_daily=30, keep_monthly=12) == [
        "gatekeeper_db-20260810T010000Z.dump"
    ]


def test_prunes_a_monthly_backup_once_it_leaves_the_monthly_window():
    names = _names("20250101T010000Z", "20260901T010000Z")

    assert to_prune(names, NOW, keep_daily=30, keep_monthly=12) == [
        "gatekeeper_db-20250101T010000Z.dump"
    ]


def test_never_prunes_a_file_it_does_not_recognise():
    names = ["README.md", MARKER] + _names("20260926T233000Z", "20240101T010000Z")

    expired = to_prune(names, NOW, keep_daily=30, keep_monthly=12)

    assert expired == ["gatekeeper_db-20240101T010000Z.dump"]


def test_never_prunes_everything_even_if_every_file_is_expired():
    names = _names("20240101T010000Z", "20240102T010000Z")

    kept = set(names) - set(to_prune(names, NOW, keep_daily=30, keep_monthly=12))

    assert kept == {"gatekeeper_db-20240102T010000Z.dump"}


def test_an_unmounted_directory_is_refused(tmp_path: Path):
    assert storage_is_mounted(tmp_path) is False


def test_a_directory_carrying_the_marker_is_accepted(tmp_path: Path):
    (tmp_path / MARKER).touch()

    assert storage_is_mounted(tmp_path) is True


def test_a_missing_directory_is_refused_rather_than_raising(tmp_path: Path):
    assert storage_is_mounted(tmp_path / "does-not-exist") is False


@pytest.mark.parametrize("keep_daily,keep_monthly", [(0, 0), (-1, -1)])
def test_a_nonsensical_retention_is_refused(keep_daily: int, keep_monthly: int):
    with pytest.raises(ValueError):
        to_prune(_names("20260926T233000Z"), NOW, keep_daily, keep_monthly)
