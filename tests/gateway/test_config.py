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
    models = load_models(Workspace(repo.path), sha)
    assert models.default == "anthropic/claude-sonnet-5-5" and models.budget_usd is None
    assert models.allowlist.allows("fake", "routing-v1") and not models.allowlist.allows("anthropic", "claude-opus-5-5")


def test_loads_budget_and_prices(repo) -> None:
    text = MODELS + "  budget_usd: 2.5\n  prices:\n    claude-sonnet-5-5: [3, 15]\n"
    sha = repo.commit({"policy.yaml": text})
    repo.approve(sha)
    models = load_models(Workspace(repo.path), sha)
    assert models.budget_usd == 2.5 and models.prices == {"claude-sonnet-5-5": (3.0, 15.0)}
    assert models.budget().limit_usd == 2.5


@pytest.mark.parametrize(
    "text",
    [
        "version: 1\n",
        "models: {default: anthropic/claude-opus-5-5, allow: [anthropic/claude-sonnet-5-5]}\n",
        "models: {default: fake/x, allow: []}\n",
        "models: {default: fake/x, allow: [fake/*], budget_usd: -1}\n",
        "models: {default: fake/x, allow: [fake/*], prices: {m: [1]}}\n",
    ],
)
def test_missing_or_inconsistent_models_are_unreadable(repo, text: str) -> None:
    sha = repo.commit({"policy.yaml": text})
    repo.approve(sha)
    with pytest.raises(RulesUnreadable):
        load_models(Workspace(repo.path), sha)
