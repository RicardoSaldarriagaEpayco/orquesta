from pathlib import Path

import pytest

from orquesta.policy.fixtures import run

OUTCOMES = run((Path(__file__).parent / "fixtures.yaml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("outcome", OUTCOMES, ids=[o.name for o in OUTCOMES])
def test_fixture_case(outcome) -> None:
    assert outcome.actual == outcome.expected


def test_fixture_covers_every_rule() -> None:
    covered = {o.expected["rule_id"] for o in OUTCOMES}
    assert covered >= {
        "self-merge", "push-protected", "pr-without-receipt", "ai-attribution", "worktree-outside-root",
        "spec-outside-root", "readonly-repo", "unknown-input", "none",
    }  # fmt: skip
