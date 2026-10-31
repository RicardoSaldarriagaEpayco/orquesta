from dataclasses import dataclass, field

import yaml

from orquesta.policy.engine import evaluate
from orquesta.policy.model import PolicyRequest, RepoFacts, Rules
from orquesta.policy.shell import inside


@dataclass
class FixtureEnvironment:
    workspace_name: str
    repos: list[dict[str, object]]
    files: dict[str, str] = field(default_factory=dict)

    def _find(self, path: str) -> dict[str, object] | None:
        matches = [r for r in self.repos if inside(path, str(r["path"]))]
        return max(matches, key=lambda r: len(str(r["path"])), default=None)

    def repo(self, path: str) -> RepoFacts | None:
        found = self._find(path)
        return RepoFacts(top=str(found["path"]), is_workspace=found.get("kind") == "workspace") if found else None

    def branch(self, top: str) -> str:
        found = self._find(top)
        return str(found.get("branch", "")) if found else ""

    def head(self, top: str, branch: str) -> str | None:
        found = self._find(top)
        heads = {str(k): str(v) for k, v in dict(found.get("heads") or {}).items()} if found else {}
        return heads.get(branch)

    def has_receipt(self, top: str, sha: str) -> bool:
        found = self._find(top)
        return bool(found) and sha in {str(r) for r in found.get("receipts") or []}

    def read_text(self, path: str) -> str | None:
        return self.files.get(path)


@dataclass
class Outcome:
    name: str
    expected: dict[str, str]
    actual: dict[str, str]

    @property
    def ok(self) -> bool:
        return self.expected == self.actual


def run(text: str, rules: Rules | None = None) -> list[Outcome]:
    if rules is not None:
        text = text.replace("{root}", rules.root)
    data = yaml.safe_load(text)
    env_data = data["environment"]
    if rules is None:
        rules = Rules.build(env_data["workspace"], data["policy"], data.get("readonly_repos") or [])
    env = FixtureEnvironment(env_data["workspace_name"], env_data["repos"], env_data.get("files") or {})
    outcomes = []
    for case in data["cases"]:
        request = PolicyRequest.model_validate({"entrypoint": "claude-wsl", "actor": "fixture", **case["request"]})
        decision = evaluate(request, rules, env, "0" * 40)
        outcomes.append(
            Outcome(case["name"], case["expect"], {"verdict": decision.verdict, "rule_id": decision.rule_id})
        )
    return outcomes
