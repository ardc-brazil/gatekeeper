from pathlib import Path

from scripts.check_tracked_secrets import production_credentials, scan


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content)
    return path


def test_reads_only_credential_named_variables(tmp_path: Path):
    _write(
        tmp_path,
        "gatekeeper.prod.env",
        "POSTGRES_PASSWORD=s3cret-value-here\nPOSTGRES_PORT=5432\nLOG_LEVEL=INFO\n",
    )

    assert production_credentials(tmp_path) == {
        "s3cret-value-here": "POSTGRES_PASSWORD"
    }


def test_ignores_usernames_so_a_shared_username_cannot_block_a_deploy(tmp_path: Path):
    _write(tmp_path, "a.prod.env", "MINIO_ROOT_USER=datamap-user\n")

    assert production_credentials(tmp_path) == {}


def test_ignores_values_too_short_to_be_a_credential(tmp_path: Path):
    _write(tmp_path, "a.prod.env", "DOI_PASSWORD=short\n")

    assert production_credentials(tmp_path) == {}


def test_strips_quotes_so_a_quoted_value_still_matches(tmp_path: Path):
    _write(tmp_path, "a.prod.env", "AUTH_FILE_UPLOAD_TOKEN_SECRET='quoted-secret'\n")

    assert production_credentials(tmp_path) == {
        "quoted-secret": "AUTH_FILE_UPLOAD_TOKEN_SECRET"
    }


def test_reads_only_live_env_files_not_dated_copies(tmp_path: Path):
    _write(tmp_path, "gatekeeper.prod.env", "DOI_PASSWORD=live-password\n")
    _write(
        tmp_path, "gatekeeper.prod.env-before-fast-api", "DOI_PASSWORD=old-password\n"
    )

    assert production_credentials(tmp_path) == {"live-password": "DOI_PASSWORD"}


def test_finds_a_credential_anywhere_in_a_tracked_file(tmp_path: Path):
    seed = _write(tmp_path, "seed.sql", "-- hashed 'leaked-secret-value'\n")

    assert scan({"leaked-secret-value": "DATAMAP_API_SECRET"}, [seed]) == [
        ("DATAMAP_API_SECRET", str(seed))
    ]


def test_reports_nothing_when_no_credential_is_tracked(tmp_path: Path):
    clean = _write(tmp_path, "config.py", "API_SECRET = os.getenv('API_SECRET')\n")

    assert scan({"leaked-secret-value": "DATAMAP_API_SECRET"}, [clean]) == []


def test_skips_a_file_it_cannot_read_rather_than_failing(tmp_path: Path):
    missing = tmp_path / "deleted.py"

    assert scan({"leaked-secret-value": "DATAMAP_API_SECRET"}, [missing]) == []
