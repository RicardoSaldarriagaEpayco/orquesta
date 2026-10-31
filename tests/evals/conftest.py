import pytest
import yaml

PROJECTS = {"ALPHA": "reviewer-agent", "BETA": "builder-agent"}


def make_suite(cases: int = 30) -> dict[str, object]:
    items = []
    for index in range(cases):
        project = "ALPHA" if index % 2 == 0 else "BETA"
        if index % 10 == 7:
            expected = {"ask": True}
        elif index % 10 == 9:
            expected = {"no_action": True}
        else:
            expected = {"agent": PROJECTS[project]}
        items.append(
            {
                "id": f"case-{index}",
                "ticket": f"{project}-{100 + index}",
                "project": project,
                "labels": ["web"],
                "summary": f"Resumen neutral del caso número {index} del proyecto.",
                "expected": expected,
                "near_miss": index % 10 == 7,
            }
        )
    return {
        "suite": "routing",
        "runs": 3,
        "engine": "test",
        "timeout_s": 60,
        "allowed_tools": ["Read"],
        "margin": 0.05,
        "cases": items,
    }


def correct_answers(data: dict[str, object]) -> dict[str, str]:
    answers = {}
    for case in data["cases"]:
        expected = case["expected"]
        answers[case["id"]] = f"agent: {expected['agent']}" if "agent" in expected else next(iter(expected))
    return answers


AGENT = "---\nname: {name}\ndescription: Atiende tickets de {project}.\n---\n"
CATALOG = """version: 1
defaults:
  owner: team
  source: workspace
  classification: internal
  egress: []
  external_effects: []
  evals: []
  approvals: []
assets:
  - id: agent/reviewer-agent
  - id: agent/builder-agent
"""
POLICY = "models:\n  default: vendor/big\n  allow: [vendor/big, fake/*]\n"


@pytest.fixture
def eval_workspace(repo):
    data = make_suite()
    sha = repo.commit(
        {
            "catalog.yaml": CATALOG,
            "policy.yaml": POLICY,
            ".claude/agents/reviewer-agent.md": AGENT.format(name="reviewer-agent", project="ALPHA"),
            ".claude/agents/builder-agent.md": AGENT.format(name="builder-agent", project="BETA"),
            "evals/routing/cases.yaml": yaml.safe_dump(data, allow_unicode=True),
        }
    )
    repo.approve(sha)
    return repo, sha, data
