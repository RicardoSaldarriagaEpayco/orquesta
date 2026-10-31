import json
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import pytest
import yaml

from orquesta.cli import main
from orquesta.errors import SuiteInvalid
from orquesta.evals import promotion
from orquesta.evals.run import interpret, run
from orquesta.evals.suite import load, parse
from orquesta.gateway.gateway import Allowlist, Gateway
from orquesta.gateway.provider import FakeProvider
from orquesta.registry.resolve import resolve
from orquesta.workspace import Workspace

from .conftest import correct_answers, make_suite

CONTRACT = json.loads((Path(__file__).parents[2] / "contracts" / "eval-case.schema.json").read_text())


class Sink:
    def __init__(self) -> None:
        self.events = []

    def write(self, event) -> None:
        self.events.append(event)


def execute(repo, sha, answers):
    workspace = Workspace(repo.path)
    suite = load(workspace, sha, "evals/routing/cases.yaml")
    provider = FakeProvider(answers)
    sink = Sink()
    gateway = Gateway(Allowlist(["fake/*"]), sink, actor="someone", tenant="acme")
    return run(suite, resolve(workspace, sha), gateway, provider, "fake-routing", sha), provider, sink


def test_generated_suite_matches_the_contract() -> None:
    jsonschema.validate(make_suite(), CONTRACT)


def test_perfect_answers_give_full_metrics(eval_workspace) -> None:
    repo, sha, data = eval_workspace
    result, _, sink = execute(repo, sha, correct_answers(data))
    assert result.metrics.accuracy == 1.0
    assert result.metrics.by_project == {"ALPHA": 1.0, "BETA": 1.0}
    assert result.metrics.ask_recall == 1.0 and result.metrics.no_action_respected == 1.0
    assert len(sink.events) == 30 * 3


def test_metrics_by_project_and_should_have_asked(eval_workspace) -> None:
    repo, sha, data = eval_workspace
    answers = correct_answers(data)
    answers["case-7"] = "agent: builder-agent"
    result, _, _ = execute(repo, sha, answers)
    assert result.metrics.ask_recall == round(2 / 3, 4)
    assert result.metrics.by_project["BETA"] < 1.0 and result.metrics.by_project["ALPHA"] == 1.0


def test_out_of_scope_passes_only_with_no_action(eval_workspace) -> None:
    repo, sha, data = eval_workspace
    answers = correct_answers(data)
    answers["case-9"] = "ask"
    result, _, _ = execute(repo, sha, answers)
    case = next(r for r in result.results if r.case_id == "case-9")
    assert case.expected == "no_action" and not case.passed
    assert result.metrics.no_action_respected < 1.0


def test_expected_answers_never_reach_the_model(eval_workspace) -> None:
    repo, sha, data = eval_workspace
    _, provider, _ = execute(repo, sha, correct_answers(data))
    assert len({call.system for call in provider.calls}) == 1
    by_id = {case["id"]: case for case in data["cases"]}
    for call in provider.calls:
        sent = call.model_dump_json()
        assert "expected" not in sent and "near_miss" not in sent
        expected = by_id[call.metadata["case_id"]]["expected"]
        assert expected.get("agent", "@@") not in call.messages[0].content


def test_majority_of_runs_decides(eval_workspace) -> None:
    repo, sha, data = eval_workspace

    class Flaky(FakeProvider):
        def complete(self, request):
            response = super().complete(request)
            if request.metadata["case_id"] == "case-0" and len(self.calls) % 3 == 1:
                return response.model_copy(update={"text": "ask"})
            return response

    workspace = Workspace(repo.path)
    suite = load(workspace, sha, "evals/routing/cases.yaml")
    gateway = Gateway(Allowlist(["fake/*"]), Sink(), actor="someone", tenant="acme")
    result = run(suite, resolve(workspace, sha), gateway, Flaky(correct_answers(data)), "fake-routing", sha)
    case = result.results[0]
    assert case.got.count("ask") == 1 and case.passed


@pytest.mark.parametrize(
    ("text", "got"),
    [
        ("agent: reviewer-agent", "agent:reviewer-agent"),
        ("Pienso que...\nAGENT: builder-agent\n", "agent:builder-agent"),
        ("ask", "ask"),
        ("no_action", "no_action"),
        ("depende", "invalid"),
    ],
)
def test_interpret(text: str, got: str) -> None:
    assert interpret(text) == got


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d["cases"].pop(),
        lambda d: d["cases"][0].update(expected={"agent": "reviewer-agent", "ask": True}),
        lambda d: d["cases"][0].update(ticket="sin-clave"),
        lambda d: d["cases"][1].update(id="case-0"),
        lambda d: d.update(runs=0),
    ],
)
def test_invalid_suite_is_rejected(change) -> None:
    data = make_suite()
    change(data)
    with pytest.raises(SuiteInvalid) as error:
        parse("cases.yaml", yaml.safe_dump(data))
    assert error.value.exit_code == 8


def test_promotion_flags_regressions_against_the_baseline(eval_workspace) -> None:
    repo, sha, data = eval_workspace
    baseline, _, _ = execute(repo, sha, correct_answers(data))
    answers = correct_answers(data)
    answers["case-0"] = "ask"
    candidate, _, _ = execute(repo, sha, answers)
    first = promotion.record(baseline, None, 0.05, reviewer="lead", at=datetime(2026, 11, 1, tzinfo=UTC))
    assert first.baseline_sha is None and first.regressions == [] and first.rollback_to is None
    second = promotion.record(candidate, baseline, 0.05, reviewer="lead")
    assert "caso case-0" in second.regressions
    assert any(r.startswith("proyecto ALPHA") for r in second.regressions)


def test_cli_eval_run_with_fake_provider_and_record(eval_workspace, tmp_path, monkeypatch, capsys) -> None:
    repo, sha, data = eval_workspace
    monkeypatch.setenv("ORQUESTA_ACTOR", "someone")
    answers = tmp_path / "answers.yaml"
    answers.write_text(yaml.safe_dump(correct_answers(data)))
    record = tmp_path / "promotion.json"
    args = ["eval", "run", "--workspace", str(repo.path), "--suite", "evals/routing/cases.yaml", "--sha", sha]
    assert main([*args, "--provider", "fake", "--answers", str(answers), "--record", str(record)]) == 0
    assert json.loads(capsys.readouterr().out)["metrics"]["accuracy"] == 1.0
    saved = json.loads(record.read_text())
    assert saved["baseline_sha"] is None and saved["candidate_sha"] == sha and saved["reviewer"] == "someone"


def test_cli_invalid_suite_exits_with_8(eval_workspace, monkeypatch) -> None:
    repo, sha, _ = eval_workspace
    monkeypatch.setenv("ORQUESTA_ACTOR", "someone")
    args = ["eval", "run", "--workspace", str(repo.path), "--suite", "evals/no-existe.yaml", "--sha", sha]
    assert main([*args, "--provider", "fake"]) == 8


def test_cli_anthropic_provider_is_not_available_yet(eval_workspace, monkeypatch, capsys) -> None:
    repo, sha, _ = eval_workspace
    monkeypatch.setenv("ORQUESTA_ACTOR", "someone")
    args = ["eval", "run", "--workspace", str(repo.path), "--suite", "evals/routing/cases.yaml", "--sha", sha]
    assert main([*args, "--provider", "anthropic"]) == 1
    assert "T064" in capsys.readouterr().err
