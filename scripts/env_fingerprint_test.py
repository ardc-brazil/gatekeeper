from pathlib import Path

from scripts.env_fingerprint import fingerprints


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content)
    return path


def test_two_files_holding_the_same_secret_report_the_same_fingerprint(tmp_path: Path):
    api = _write(tmp_path, "api.env", "AUTH_FILE_UPLOAD_TOKEN_SECRET=shared-value\n")
    web = _write(tmp_path, "web.env", "AUTH_FILE_UPLOAD_TOKEN_SECRET=shared-value\n")

    assert fingerprints(api, ["AUTH_FILE_UPLOAD_TOKEN_SECRET"]) == fingerprints(
        web, ["AUTH_FILE_UPLOAD_TOKEN_SECRET"]
    )


def test_a_mismatch_is_visible(tmp_path: Path):
    api = _write(tmp_path, "api.env", "AUTH_FILE_UPLOAD_TOKEN_SECRET=one\n")
    web = _write(tmp_path, "web.env", "AUTH_FILE_UPLOAD_TOKEN_SECRET=two\n")

    assert fingerprints(api, ["AUTH_FILE_UPLOAD_TOKEN_SECRET"]) != fingerprints(
        web, ["AUTH_FILE_UPLOAD_TOKEN_SECRET"]
    )


def test_strips_surrounding_quotes_so_quoting_does_not_look_like_a_mismatch(
    tmp_path: Path,
):
    plain = _write(tmp_path, "a.env", "DOI_PASSWORD=value\n")
    quoted = _write(tmp_path, "b.env", "DOI_PASSWORD='value'\n")

    assert fingerprints(plain, ["DOI_PASSWORD"]) == fingerprints(
        quoted, ["DOI_PASSWORD"]
    )


def test_reports_a_variable_that_is_absent_rather_than_omitting_it(tmp_path: Path):
    path = _write(tmp_path, "a.env", "LOG_LEVEL=INFO\n")

    assert fingerprints(path, ["DOI_PASSWORD"]) == {"DOI_PASSWORD": "absent"}


def test_never_returns_the_value(tmp_path: Path):
    path = _write(tmp_path, "a.env", "DOI_PASSWORD=super-secret\n")

    assert "super-secret" not in str(fingerprints(path, ["DOI_PASSWORD"]))
