import os
import re
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Literal, Protocol

Verdict = Literal["allow", "deny", "ask"]


ENTRYPOINTS = ("claude-wsl", "claude-desktop", "ci", "platform")


class InvalidRequest(ValueError):
    pass


@dataclass(frozen=True)
class PolicyRequest:
    entrypoint: str
    tool: str
    input: dict[str, object]
    cwd: str
    actor: str

    @classmethod
    def from_dict(cls, data: object) -> "PolicyRequest":
        if not isinstance(data, dict):
            raise InvalidRequest("PolicyRequest debe ser un objeto JSON")
        extra = set(data) - {"entrypoint", "tool", "input", "cwd", "actor"}
        if extra:
            raise InvalidRequest(f"campos desconocidos: {', '.join(sorted(extra))}")
        if data.get("entrypoint") not in ENTRYPOINTS:
            raise InvalidRequest(f"entrypoint debe ser uno de {', '.join(ENTRYPOINTS)}")
        for name in ("tool", "cwd", "actor"):
            if not isinstance(data.get(name), str) or not data[name]:
                raise InvalidRequest(f"{name} debe ser un texto no vacío")
        if not isinstance(data.get("input"), dict):
            raise InvalidRequest("input debe ser un objeto")
        return cls(data["entrypoint"], data["tool"], data["input"], data["cwd"], data["actor"])


@dataclass(frozen=True)
class PolicyDecision:
    verdict: Verdict
    rule_id: str
    reason: str
    policy_sha: str

    def to_dict(self) -> dict[str, str]:
        return {"verdict": self.verdict, "rule_id": self.rule_id, "reason": self.reason, "policy_sha": self.policy_sha}


@dataclass(frozen=True)
class Rules:
    root: str
    protected_branches: frozenset[str]
    local_branches: tuple[str, ...]
    attribution: tuple[re.Pattern[str], ...]
    pr_requires_receipt: bool
    readonly_repos: tuple[str, ...]
    receipt_keys: tuple[str, ...] = ()

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
            receipt_keys=tuple(str(k) for k in policy.get("receipt_public_keys") or ()),
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
