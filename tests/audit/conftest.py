import secrets
from pathlib import Path

import psycopg
import pytest


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
