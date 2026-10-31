import os
import re
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

Verdict = Literal["allow", "deny", "ask"]
Entrypoint = Literal["claude-wsl", "claude-desktop", "ci", "platform"]


class PolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entrypoint: Entrypoint
    tool: str = Field(min_length=1)
    input: dict[str, object]
    cwd: str = Field(min_length=1)
    actor: str = Field(min_length=1)


class PolicyDecision(BaseModel):
    verdict: Verdict
    rule_id: str
    reason: str
    policy_sha: str


@dataclass(frozen=True)
class Rules:
    root: str
    protected_branches: frozenset[str]
    local_branches: tuple[str, ...]
    attribution: tuple[re.Pattern[str], ...]
    pr_requires_receipt: bool
    readonly_repos: tuple[str, ...]

    @classmethod
    def build(cls, workspace_root: str, policy: dict[str, object], readonly: list[str]) -> "Rules":
        root = os.path.normpath(os.path.join(os.path.dirname(workspace_root.rstrip("/")), str(policy["worktree_root"])))
        return cls(
            root=root,
            protected_branches=frozenset(policy["protected_branches"]),
            local_branches=tuple(policy.get("local_branches") or ()),
            attribution=tuple(re.compile(p, re.IGNORECASE) for p in policy["ai_attribution_patterns"]),
            pr_requires_receipt=bool(policy["pr_requires_receipt"]),
            readonly_repos=tuple(readonly),
        )

    def protected(self, branch: str) -> bool:
        return branch in self.protected_branches or any(fnmatch(branch, p) for p in self.local_branches)


@dataclass(frozen=True)
class RepoFacts:
    top: str
    is_workspace: bool


class Environment(Protocol):
    workspace_name: str

    def repo(self, path: str) -> RepoFacts | None: ...

    def branch(self, top: str) -> str: ...

    def head(self, top: str, branch: str) -> str | None: ...

    def has_receipt(self, top: str, sha: str) -> bool: ...

    def read_text(self, path: str) -> str | None: ...
