import re
from collections import defaultdict

from pydantic import BaseModel, Field

from orquesta.evals.suite import EpisodeChecks, EvalSuite

CHECKS = ("tools_allowed", "tools_required", "final_pattern", "receipts")


class EpisodeTrace(BaseModel):
    tools_used: list[str] = Field(default_factory=list)
    final_message: str = ""
    receipts: list[str] = Field(default_factory=list)


class EpisodeResult(BaseModel):
    case_id: str
    project: str
    checks: dict[str, bool]
    passed: bool


class EpisodeRun(BaseModel):
    suite: str
    results: list[EpisodeResult]
    by_check: dict[str, float]
    by_project: dict[str, float]
    accuracy: float


def score(checks: EpisodeChecks, trace: EpisodeTrace | None) -> dict[str, bool]:
    if trace is None:
        return {name: False for name in CHECKS if _declared(checks, name)}
    outcome = {}
    if checks.tools_allowed is not None:
        outcome["tools_allowed"] = set(trace.tools_used) <= set(checks.tools_allowed)
    if checks.tools_required:
        outcome["tools_required"] = set(checks.tools_required) <= set(trace.tools_used)
    if checks.final_pattern:
        outcome["final_pattern"] = re.search(checks.final_pattern, trace.final_message, re.MULTILINE) is not None
    if checks.receipts:
        outcome["receipts"] = set(checks.receipts) <= set(trace.receipts)
    return outcome


def _declared(checks: EpisodeChecks, name: str) -> bool:
    value = getattr(checks, name)
    return value is not None if name == "tools_allowed" else bool(value)


def _rate(values: list[bool]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def evaluate(suite: EvalSuite, traces: dict[str, EpisodeTrace]) -> EpisodeRun:
    results = []
    for case in suite.cases:
        if case.checks is None:
            continue
        outcome = score(case.checks, traces.get(case.id))
        results.append(
            EpisodeResult(case_id=case.id, project=case.project, checks=outcome, passed=all(outcome.values()))
        )
    by_check: dict[str, list[bool]] = defaultdict(list)
    by_project: dict[str, list[bool]] = defaultdict(list)
    for result in results:
        for name, ok in result.checks.items():
            by_check[name].append(ok)
        by_project[result.project].append(result.passed)
    return EpisodeRun(
        suite=suite.suite,
        results=results,
        by_check={name: _rate(values) for name, values in sorted(by_check.items())},
        by_project={name: _rate(values) for name, values in sorted(by_project.items())},
        accuracy=_rate([r.passed for r in results]),
    )
