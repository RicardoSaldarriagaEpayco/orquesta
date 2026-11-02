import os
import secrets
import shutil
import subprocess
import time
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[1]
POSTGRES_IMAGE = "postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


class Repo:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.mkdir(parents=True)
        self.git("init", "-q", "-b", "main")

    def git(self, *args: str) -> str:
        env = {**os.environ, **GIT_ENV}
        return subprocess.run(
            ["git", "-C", str(self.path), *args], capture_output=True, text=True, check=True, env=env
        ).stdout.strip()

    def commit(self, files: dict[str, str], message: str = "c") -> str:
        for name, content in files.items():
            target = self.path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def approve(self, sha: str) -> None:
        self.git("update-ref", "refs/remotes/origin/main", sha)


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    return Repo(tmp_path / "workspace")


CATALOG = """version: 1
defaults:
  owner: platform-team
  source: workspace
  classification: internal
  egress: []
  external_effects: []
  evals: []
  expires: null
  approvals: []
assets:
  - id: agent/reviewer
    evals: [routing]
  - id: skill/ship
    external_effects: [commit, push, pr]
  - id: skill/vendored
    source: {url: https://example.com/vendor/kit, commit: 0123456789abcdef0123456789abcdef01234567}
    license: MIT
"""

FILES = {
    "catalog.yaml": CATALOG,
    ".claude/agents/reviewer.md": "---\nname: reviewer\ndescription: Revisa.\ntools: Read, Grep\n---\n\nCuerpo.\n",
    ".claude/skills/ship/SKILL.md": "---\nname: ship\ndescription: Sube.\ndisable-model-invocation: true\n---\n",
    ".claude/skills/ship/reference.md": "detalle\n",
    ".claude/skills/vendored/SKILL.md": '---\nname: "vendored"\ndescription: De terceros.\n---\n',
    "README.md": "fuera de .claude\n",
}


@pytest.fixture
def workspace(repo: Repo) -> Repo:
    repo.approve(repo.commit(FILES))
    return repo


def _docker(*args: str) -> str:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=True, timeout=120).stdout.strip()


def _wait(dsn: str) -> None:
    deadline = time.monotonic() + 60
    while True:
        try:
            psycopg.connect(dsn, connect_timeout=2).close()
            return
        except psycopg.OperationalError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)


@pytest.fixture(scope="session")
def postgres() -> dict[str, str]:
    if os.environ.get("ORQUESTA_TEST_OWNER_DSN"):
        yield {
            "owner": os.environ["ORQUESTA_TEST_OWNER_DSN"],
            "writer": os.environ["ORQUESTA_TEST_WRITER_DSN"],
            "graph": os.environ["ORQUESTA_TEST_GRAPH_DSN"],
        }
        return
    if not shutil.which("docker"):
        pytest.skip("sin docker para levantar Postgres")
    passwords = {role: secrets.token_hex(12) for role in ("owner", "writer", "graph")}
    initdb = ROOT / "docker" / "initdb"
    container = _docker(
        "run", "-d", "--rm",
        "-e", "POSTGRES_USER=audit_owner", "-e", "POSTGRES_DB=audit",
        "-e", f"POSTGRES_PASSWORD={passwords['owner']}",
        "-e", f"AUDIT_WRITER_PASSWORD={passwords['writer']}",
        "-e", f"GRAPH_WRITER_PASSWORD={passwords['graph']}",
        "-v", f"{initdb}/10-schema.sh:/docker-entrypoint-initdb.d/10-schema.sh:ro",
        "-v", f"{initdb}/20-graph.sh:/docker-entrypoint-initdb.d/20-graph.sh:ro",
        "-v", f"{ROOT}/src/orquesta/audit/schema.sql:/docker-entrypoint-initdb.d/schema.sql.in:ro",
        "-p", "127.0.0.1::5432", POSTGRES_IMAGE,
    )  # fmt: skip
    try:
        port = _docker("port", container, "5432/tcp").splitlines()[0].rsplit(":", 1)[1]
        users = {"owner": "audit_owner", "writer": "audit_writer", "graph": "graph_writer"}
        dsns = {role: f"postgresql://{users[role]}:{passwords[role]}@127.0.0.1:{port}/audit" for role in users}
        _wait(dsns["graph"])
        yield dsns
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=60)


@pytest.fixture(scope="session")
def database(postgres: dict[str, str]) -> tuple[str, str]:
    return postgres["owner"], postgres["writer"]
