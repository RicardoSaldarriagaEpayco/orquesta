import os
import subprocess
from pathlib import Path

import pytest

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
