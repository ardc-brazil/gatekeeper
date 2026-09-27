from pathlib import Path

from scripts.compare_env_files import Difference, compare, read_env


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content)
    return path


def test_reads_assignments_and_ignores_comments_and_blank_lines(tmp_path: Path):
    path = _write(tmp_path, "a.env", "# a comment\n\nA=1\n\n# another\nB=2\n\n")

    assert read_env(path) == {"A": "1", "B": "2"}


def test_strips_surrounding_quotes_so_quoting_is_not_a_difference(tmp_path: Path):
    plain = _write(tmp_path, "a.env", "A=value\n")
    quoted = _write(tmp_path, "b.env", "A='value'\n")

    assert compare(plain, quoted) == []


def test_identical_files_have_no_differences(tmp_path: Path):
    a = _write(tmp_path, "a.env", "A=1\nB=2\n")
    b = _write(tmp_path, "b.env", "B=2\nA=1\n")

    assert compare(a, b) == []


def test_order_is_not_a_difference(tmp_path: Path):
    a = _write(tmp_path, "a.env", "A=1\nB=2\n")
    b = _write(tmp_path, "b.env", "B=2\nA=1\n")

    assert compare(a, b) == []


def test_a_changed_value_is_reported_without_revealing_it(tmp_path: Path):
    a = _write(tmp_path, "a.env", "SECRET=the-real-one\n")
    b = _write(tmp_path, "b.env", "SECRET=something-else\n")

    differences = compare(a, b)

    assert differences == [Difference("SECRET", "value differs")]
    assert "the-real-one" not in str(differences)
    assert "something-else" not in str(differences)


def test_a_key_missing_from_the_second_file_is_reported(tmp_path: Path):
    a = _write(tmp_path, "a.env", "A=1\nB=2\n")
    b = _write(tmp_path, "b.env", "A=1\n")

    assert compare(a, b) == [Difference("B", "missing from the second file")]


def test_a_key_only_in_the_second_file_is_reported(tmp_path: Path):
    a = _write(tmp_path, "a.env", "A=1\n")
    b = _write(tmp_path, "b.env", "A=1\nB=2\n")

    assert compare(a, b) == [Difference("B", "missing from the first file")]


def test_every_difference_is_reported_not_only_the_first(tmp_path: Path):
    a = _write(tmp_path, "a.env", "A=1\nB=2\nC=3\n")
    b = _write(tmp_path, "b.env", "A=9\nB=2\nD=4\n")

    assert compare(a, b) == [
        Difference("A", "value differs"),
        Difference("C", "missing from the second file"),
        Difference("D", "missing from the first file"),
    ]


def test_an_empty_value_is_not_the_same_as_a_missing_key(tmp_path: Path):
    a = _write(tmp_path, "a.env", "A=\n")
    b = _write(tmp_path, "b.env", "B=1\n")

    assert compare(a, b) == [
        Difference("A", "missing from the second file"),
        Difference("B", "missing from the first file"),
    ]


def test_an_export_prefix_is_read_as_the_same_variable(tmp_path: Path):
    a = _write(tmp_path, "a.env", "A=1\n")
    b = _write(tmp_path, "b.env", "export A=1\n")

    assert compare(a, b) == []
