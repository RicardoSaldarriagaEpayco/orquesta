import json
from pathlib import Path

import jsonschema
import pytest
import yaml

from orquesta.errors import SuiteInvalid
from orquesta.evals.episodes import EpisodeTrace, evaluate
from orquesta.evals.suite import parse

from .conftest import make_suite

CONTRACT = json.loads((Path(__file__).parents[2] / "contracts" / "eval-case.schema.json").read_text())
CHECKS = {
    "tools_allowed": ["Read", "Grep", "Bash"],
    "tools_required": ["Bash"],
    "final_pattern": r"^PR: https://\S+$",
    "receipts": ["ready"],
}


def suite_with_checks():
    data = make_suite()
    data["cases"][0]["checks"] = CHECKS
    data["cases"][1]["checks"] = {"final_pattern": "no_action"}
    jsonschema.validate(data, CONTRACT)
    return parse("cases.yaml", yaml.safe_dump(data))


def good() -> EpisodeTrace:
    return EpisodeTrace(
        tools_used=["Read", "Bash"], final_message="Listo.\nPR: https://example.com/pr/1", receipts=["ready"]
    )


def test_only_cases_with_checks_are_scored() -> None:
    run = evaluate(suite_with_checks(), {"case-0": good(), "case-1": EpisodeTrace(final_message="no_action")})
    assert [r.case_id for r in run.results] == ["case-0", "case-1"]
    assert run.accuracy == 1.0 and run.by_check == {
        "final_pattern": 1.0,
        "receipts": 1.0,
        "tools_allowed": 1.0,
        "tools_required": 1.0,
    }


@pytest.mark.parametrize(
    ("change", "failed"),
    [
        ({"tools_used": ["Read", "Bash", "Write"]}, "tools_allowed"),
        ({"tools_used": ["Read"]}, "tools_required"),
        ({"final_message": "Listo, sin PR"}, "final_pattern"),
        ({"receipts": []}, "receipts"),
    ],
)
def test_each_check_fails_on_its_own(change, failed) -> None:
    trace = good().model_copy(update=change)
    run = evaluate(suite_with_checks(), {"case-0": trace, "case-1": EpisodeTrace(final_message="no_action")})
    result = run.results[0]
    assert not result.passed and [n for n, ok in result.checks.items() if not ok] == [failed]
    assert run.by_check[failed] < 1.0 and run.by_project["ALPHA"] == 0.0


def test_a_missing_trace_fails_every_declared_check() -> None:
    run = evaluate(suite_with_checks(), {})
    assert run.results[0].checks == {name: False for name in CHECKS}
    assert run.results[1].checks == {"final_pattern": False}


def test_unknown_check_is_an_invalid_suite() -> None:
    data = make_suite()
    data["cases"][0]["checks"] = {"tools_forbidden": ["Write"]}
    with pytest.raises(SuiteInvalid):
        parse("cases.yaml", yaml.safe_dump(data))
