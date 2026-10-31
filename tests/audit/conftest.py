import os
import secrets
import shutil
import subprocess
import time
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[2]
IMAGE = "postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea"


def _docker(*args: str) -> str:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=True, timeout=120).stdout.strip()


@pytest.fixture(scope="session")
def database():
    if os.environ.get("ORQUESTA_TEST_OWNER_DSN"):
        yield os.environ["ORQUESTA_TEST_OWNER_DSN"], os.environ["ORQUESTA_TEST_WRITER_DSN"]
        return
    if not shutil.which("docker"):
        pytest.skip("sin docker para levantar Postgres")
    owner, writer = secrets.token_hex(12), secrets.token_hex(12)
    container = _docker(
        "run", "-d", "--rm",
        "-e", "POSTGRES_USER=audit_owner", "-e", "POSTGRES_DB=audit",
        "-e", f"POSTGRES_PASSWORD={owner}", "-e", f"AUDIT_WRITER_PASSWORD={writer}",
        "-v", f"{ROOT}/docker/initdb/10-schema.sh:/docker-entrypoint-initdb.d/10-schema.sh:ro",
        "-v", f"{ROOT}/src/orquesta/audit/schema.sql:/docker-entrypoint-initdb.d/schema.sql.in:ro",
        "-p", "127.0.0.1::5432", IMAGE,
    )  # fmt: skip
    try:
        port = _docker("port", container, "5432/tcp").splitlines()[0].rsplit(":", 1)[1]
        writer_dsn = f"postgresql://audit_writer:{writer}@127.0.0.1:{port}/audit"
        owner_dsn = f"postgresql://audit_owner:{owner}@127.0.0.1:{port}/audit"
        deadline = time.monotonic() + 60
        while True:
            try:
                psycopg.connect(writer_dsn, connect_timeout=2).close()
                break
            except psycopg.OperationalError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.5)
        yield owner_dsn, writer_dsn
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=60)


@pytest.fixture
def dsns(database):
    owner_dsn, writer_dsn = database
    with psycopg.connect(owner_dsn, autocommit=True) as conn:
        conn.execute("TRUNCATE audit_events RESTART IDENTITY")
    return owner_dsn, writer_dsn


@pytest.fixture
def key_file(tmp_path: Path) -> Path:
    path = tmp_path / "audit.key"
    path.write_text(secrets.token_hex(32))
    path.chmod(0o600)
    return path
