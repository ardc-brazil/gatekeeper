from datetime import datetime, timezone
from pathlib import Path

from scripts.backup_metrics import render, write

NOW = datetime(2026, 9, 26, 23, 54, 19, tzinfo=timezone.utc)


def test_reports_when_the_last_backup_succeeded():
    text = render(NOW, size_bytes=26_423_296, kept=3)

    assert "datamap_backup_last_success_timestamp_seconds 1790466859" in text


def test_reports_the_size_and_how_many_are_kept():
    text = render(NOW, size_bytes=26_423_296, kept=3)

    assert "datamap_backup_last_size_bytes 26423296" in text
    assert "datamap_backup_kept 3" in text


def test_every_metric_is_declared_so_prometheus_does_not_guess():
    text = render(NOW, size_bytes=1, kept=1)

    for metric in (
        "datamap_backup_last_success_timestamp_seconds",
        "datamap_backup_last_size_bytes",
        "datamap_backup_kept",
    ):
        assert f"# HELP {metric} " in text
        assert f"# TYPE {metric} gauge" in text


def test_ends_with_a_newline_because_the_collector_needs_one():
    assert render(NOW, size_bytes=1, kept=1).endswith("\n")


def test_writing_leaves_no_partial_file_behind(tmp_path: Path):
    target = tmp_path / "backup.prom"

    write(target, NOW, size_bytes=1, kept=1)

    assert target.exists()
    assert list(tmp_path.iterdir()) == [target]


def test_writing_replaces_the_previous_value(tmp_path: Path):
    target = tmp_path / "backup.prom"

    write(target, NOW, size_bytes=1, kept=1)
    write(target, NOW, size_bytes=999, kept=7)

    text = target.read_text()
    assert "datamap_backup_last_size_bytes 999" in text
    assert "datamap_backup_last_size_bytes 1\n" not in text


def test_a_missing_directory_does_not_fail_the_backup(tmp_path: Path):
    target = tmp_path / "does-not-exist" / "backup.prom"

    assert write(target, NOW, size_bytes=1, kept=1) is False


def test_a_successful_write_says_so(tmp_path: Path):
    assert write(tmp_path / "backup.prom", NOW, size_bytes=1, kept=1) is True
