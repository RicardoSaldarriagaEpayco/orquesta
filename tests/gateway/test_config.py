import pytest

from orquesta.gateway.config import load_models
from orquesta.policy.load import RulesUnreadable
from orquesta.workspace import Workspace

MODELS = """models:
  default: anthropic/claude-sonnet-5-5
  allow:
    - anthropic/claude-sonnet-5-5
    - fake/*
"""


def test_loads_the_allowlist_from_the_approved_sha(repo) -> None:
    sha = repo.commit({"policy.yaml": MODELS})
    repo.approve(sha)
    (repo.path / "policy.yaml").write_text("models: {default: x/y, allow: [x/y]}\n")
    allowlist, default = load_models(Workspace(repo.path), sha)
    assert default == "anthropic/claude-sonnet-5-5"
    assert allowlist.allows("fake", "routing-v1") and not allowlist.allows("anthropic", "claude-opus-5-5")


@pytest.mark.parametrize(
    "text",
    [
        "version: 1\n",
        "models: {default: anthropic/claude-opus-5-5, allow: [anthropic/claude-sonnet-5-5]}\n",
        "models: {default: fake/x, allow: []}\n",
    ],
)
def test_missing_or_inconsistent_models_are_unreadable(repo, text: str) -> None:
    sha = repo.commit({"policy.yaml": text})
    repo.approve(sha)
    with pytest.raises(RulesUnreadable):
        load_models(Workspace(repo.path), sha)
