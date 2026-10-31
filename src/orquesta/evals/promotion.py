from datetime import UTC, datetime

from pydantic import BaseModel, Field

from orquesta.evals.run import EvalRun, Metrics

HEX40 = r"^[0-9a-f]{40}$"


class PromotionRecord(BaseModel):
    candidate_sha: str = Field(pattern=HEX40)
    baseline_sha: str | None = Field(default=None, pattern=HEX40)
    suite: str
    metrics: Metrics
    regressions: list[str]
    margin: float = Field(ge=0.0, le=1.0)
    reviewer: str | None = None
    rollback_to: str | None = Field(default=None, pattern=HEX40)
    at: datetime


def regressions(candidate: EvalRun, baseline: EvalRun | None, margin: float) -> list[str]:
    if baseline is None:
        return []
    before = {r.case_id: r.passed for r in baseline.results}
    found = [f"caso {r.case_id}" for r in candidate.results if before.get(r.case_id) and not r.passed]
    for project, rate in baseline.metrics.by_project.items():
        now = candidate.metrics.by_project.get(project, 0.0)
        if rate - now > margin:
            found.append(f"proyecto {project}: {rate:.2%} -> {now:.2%}")
    return found


def record(
    candidate: EvalRun, baseline: EvalRun | None, margin: float, reviewer: str | None = None, at: datetime | None = None
) -> PromotionRecord:
    return PromotionRecord(
        candidate_sha=candidate.asset_set_sha,
        baseline_sha=baseline.asset_set_sha if baseline else None,
        suite=candidate.suite,
        metrics=candidate.metrics,
        regressions=regressions(candidate, baseline, margin),
        margin=margin,
        reviewer=reviewer,
        rollback_to=baseline.asset_set_sha if baseline else None,
        at=at or datetime.now(UTC),
    )
