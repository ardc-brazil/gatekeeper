import subprocess

POSTGRES_CONTAINER = "datamap_postgres_test_integration"


def execute(sql: str) -> str:
    result = subprocess.run(
        [
            "docker",
            "exec",
            POSTGRES_CONTAINER,
            "psql",
            "-U",
            "gk_admin",
            "-d",
            "gatekeeper_db",
            "-v",
            "ON_ERROR_STOP=1",
            "-tA",
            "-c",
            sql,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()
