import subprocess
from pathlib import Path, PurePosixPath

from orquesta.errors import ShaNotApproved

APPROVED_REF = "origin/main"


class Workspace:
    def __init__(self, path: Path | str, approved_ref: str = APPROVED_REF) -> None:
        self.path = Path(path)
        self.approved_ref = approved_ref
        self._resolved: dict[str, str] = {}

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", "-C", str(self.path), *args], capture_output=True, text=True, timeout=60)

    def resolve(self, sha: str) -> str:
        if sha not in self._resolved:
            self._resolved[sha] = self._resolve(sha)
        return self._resolved[sha]

    def _resolve(self, sha: str) -> str:
        commit = self._git("rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}")
        if commit.returncode != 0 or sha.startswith("-"):
            raise ShaNotApproved(sha, self.approved_ref)
        full = commit.stdout.strip()
        if self._git("merge-base", "--is-ancestor", full, self.approved_ref).returncode != 0:
            raise ShaNotApproved(sha, self.approved_ref)
        return full

    def read(self, sha: str, path: str) -> str:
        relative = _checked(path)
        result = self._git("show", f"{self.resolve(sha)}:{relative}")
        if result.returncode != 0:
            raise FileNotFoundError(f"{relative} no existe en {sha}")
        return result.stdout

    def tree(self, sha: str, path: str) -> str:
        result = self._git("ls-tree", "-r", "--full-tree", self.resolve(sha), "--", _checked(path))
        return result.stdout

    def list(self, sha: str, prefix: str) -> list[str]:
        result = self._git("ls-tree", "-r", "--name-only", self.resolve(sha), "--", _checked(prefix))
        return [line for line in result.stdout.splitlines() if line]


def _checked(path: str) -> str:
    candidate = PurePosixPath(path.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise ValueError(f"ruta fuera del workspace: {path}")
    return candidate.as_posix()
