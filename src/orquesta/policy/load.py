import os
import subprocess
from dataclasses import dataclass, field

import yaml

from orquesta.errors import OrquestaError, ShaNotApproved
from orquesta.policy.model import RepoFacts, Rules
from orquesta.workspace import Workspace


class RulesUnreadable(OrquestaError):
    exit_code = 3

    def __init__(self, reason: str) -> None:
        super().__init__(f"reglas del tenant ilegibles: {reason}")


class RequestUnreadable(OrquestaError):
    exit_code = 2

    def __init__(self, reason: str) -> None:
        super().__init__(f"PolicyRequest ilegible: {reason}")


def load_rules(workspace: Workspace, sha: str) -> tuple[Rules, str]:
    try:
        full = workspace.resolve(sha)
        loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
        policy = yaml.load(workspace.read(full, "policy.yaml"), Loader=loader)
        manifest = yaml.load(workspace.read(full, "workspace.yaml"), Loader=loader)
        readonly = [str(repo["name"]) for repo in manifest["repos"] if repo.get("write") is False]
        return Rules.build(main_checkout(str(workspace.path.resolve())), policy, readonly), full
    except ShaNotApproved as error:
        raise RulesUnreadable(str(error)) from error
    except (FileNotFoundError, yaml.YAMLError, KeyError, TypeError, AttributeError, ValueError) as error:
        raise RulesUnreadable(f"{type(error).__name__}: {error}") from error


def _git(path: str, *args: str) -> str:
    try:
        result = subprocess.run(["git", "-C", path, *args], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def main_checkout(path: str) -> str:
    common = _git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common and os.path.basename(common.rstrip("/")) == ".git":
        return os.path.dirname(common.rstrip("/"))
    return path


@dataclass
class GitEnvironment:
    workspace: str
    workspace_name: str = ""
    _common: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self._common = os.path.realpath(_git(self.workspace, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        if not self.workspace_name:
            url = _git(self.workspace, "remote", "get-url", "origin")
            self.workspace_name = url.rstrip("/").removesuffix(".git").split("/")[-1].split(":")[-1]

    def repo(self, path: str) -> RepoFacts | None:
        probe = path
        while not os.path.isdir(probe) and probe != os.path.dirname(probe):
            probe = os.path.dirname(probe)
        top = _git(probe, "rev-parse", "--show-toplevel")
        if not top:
            return None
        common = os.path.realpath(_git(probe, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        return RepoFacts(top=top, is_workspace=common == self._common)

    def branch(self, top: str) -> str:
        return _git(top, "branch", "--show-current")

    def head(self, top: str, branch: str) -> str | None:
        for ref in (f"refs/remotes/origin/{branch}", f"refs/heads/{branch}"):
            if sha := _git(top, "rev-parse", "--verify", "-q", ref):
                return sha
        return None

    def has_receipt(self, top: str, sha: str) -> bool:
        common = _git(top, "rev-parse", "--path-format=absolute", "--git-common-dir")
        return bool(common) and os.path.exists(os.path.join(common, "epw-ready", sha))

    def read_text(self, path: str) -> str | None:
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                return handle.read()
        except OSError:
            return None
