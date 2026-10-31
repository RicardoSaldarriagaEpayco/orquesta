import re
from collections import defaultdict
from collections.abc import Sequence

from pydantic import BaseModel

from orquesta.evals.suite import EvalCase, EvalSuite, outcome
from orquesta.gateway.gateway import Gateway
from orquesta.gateway.provider import ModelProvider, ModelRequest
from orquesta.registry.models import AgentAssetManifest

ANSWER = re.compile(
    r"^\s*(agent:\s*(?P<agent>[a-z0-9-]+)|(?P<ask>ask)|(?P<none>no_action))\s*$", re.IGNORECASE | re.MULTILINE
)
INSTRUCTIONS = """Eres el enrutador de tickets de un equipo de ingeniería. Para el ticket que recibas, responde con una
sola línea y nada más:
- agent: <nombre>  si uno de los agentes de la lista corresponde sin ambigüedad;
- ask              si el ticket es ambiguo y hay que preguntar antes de elegir;
- no_action        si el ticket está fuera del alcance de todos los agentes.

Agentes disponibles:
"""


class CaseResult(BaseModel):
    case_id: str
    project: str
    expected: str
    got: list[str]
    passed: bool


class Metrics(BaseModel):
    accuracy: float
    by_project: dict[str, float]
    ask_recall: float | None
    no_action_respected: float | None


class EvalRun(BaseModel):
    suite: str
    asset_set_sha: str
    provider: str
    model: str
    runs: int
    results: list[CaseResult]
    metrics: Metrics


def system_prompt(agents: Sequence[AgentAssetManifest]) -> str:
    lines = [f"- {a.name}: {a.description or ''}".rstrip() for a in sorted(agents, key=lambda a: a.name)]
    return INSTRUCTIONS + "\n".join(lines)


def user_prompt(case: EvalCase) -> str:
    labels = ", ".join(case.labels) or "(sin labels)"
    return f"Ticket {case.ticket} del proyecto {case.project}. Labels: {labels}.\nResumen: {case.summary}"


def interpret(text: str) -> str:
    match = ANSWER.search(text)
    if not match:
        return "invalid"
    if match.group("agent"):
        return f"agent:{match.group('agent').lower()}"
    return "ask" if match.group("ask") else "no_action"


def _rate(results: list[CaseResult]) -> float | None:
    return round(sum(r.passed for r in results) / len(results), 4) if results else None


def metrics(results: list[CaseResult]) -> Metrics:
    by_project: dict[str, list[CaseResult]] = defaultdict(list)
    for result in results:
        by_project[result.project].append(result)
    return Metrics(
        accuracy=_rate(results) or 0.0,
        by_project={project: _rate(items) or 0.0 for project, items in sorted(by_project.items())},
        ask_recall=_rate([r for r in results if r.expected == "ask"]),
        no_action_respected=_rate([r for r in results if r.expected == "no_action"]),
    )


def run(
    suite: EvalSuite,
    agents: Sequence[AgentAssetManifest],
    gateway: Gateway,
    provider: ModelProvider,
    model: str,
    asset_set_sha: str,
) -> EvalRun:
    system = system_prompt([a for a in agents if a.type == "agent"])
    results = []
    for case in suite.cases:
        request = ModelRequest(
            model=model,
            system=system,
            messages=[{"role": "user", "content": user_prompt(case)}],
            max_tokens=32,
            metadata={"case_id": case.id},
        )
        got = [interpret(gateway.complete(provider, request).text) for _ in range(suite.runs)]
        expected = outcome(case.expected)
        passed = sum(answer == expected for answer in got) * 2 > suite.runs
        results.append(CaseResult(case_id=case.id, project=case.project, expected=expected, got=got, passed=passed))
    return EvalRun(
        suite=suite.suite,
        asset_set_sha=asset_set_sha,
        provider=provider.name(),
        model=model,
        runs=suite.runs,
        results=results,
        metrics=metrics(results),
    )
