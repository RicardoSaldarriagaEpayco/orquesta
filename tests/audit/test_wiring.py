import io
import json

import psycopg
import pytest
import yaml

from orquesta.cli import main

POLICY = """version: 1
protected_branches: [main]
worktree_root: workspace/
spec_root: workspace/specs/
ai_attribution_patterns: ['generated with \\[?claude code']
pr_requires_receipt: true
models: {default: vendor/big, allow: [vendor/big, fake/*]}
"""
WORKSPACE = "version: 1\ntenant: acme\nrepos:\n  - {name: infra, write: false}\n"
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
"""
AGENT = "---\nname: reviewer-agent\ndescription: Revisa.\n---\n"


@pytest.fixture
def tenant_repo(repo, monkeypatch):
    from ..evals.conftest import make_suite

    data = make_suite()
    for case in data["cases"]:
        if "agent" in case["expected"]:
            case["expected"] = {"agent": "reviewer-agent"}
    sha = repo.commit(
        {
            "policy.yaml": POLICY,
            "workspace.yaml": WORKSPACE,
            "catalog.yaml": CATALOG,
            ".claude/agents/reviewer-agent.md": AGENT,
            "evals/routing/cases.yaml": yaml.safe_dump(data),
        }
    )
    repo.approve(sha)
    monkeypatch.setenv("ORQUESTA_ACTOR", "someone")
    return repo, sha


@pytest.fixture
def audited(dsns, key_file, monkeypatch):
    owner, writer = dsns
    monkeypatch.setenv("ORQUESTA_AUDIT_DSN", writer)
    monkeypatch.setenv("ORQUESTA_AUDIT_KEY", str(key_file))
    return owner


def rows(owner: str) -> list[dict]:
    with psycopg.connect(owner) as conn:
        return [r[0] for r in conn.execute("SELECT row_to_json(e) FROM audit_events e ORDER BY seq").fetchall()]


def policy_eval(repo, sha, monkeypatch, capsys) -> int:
    request = {
        "entrypoint": "claude-wsl",
        "tool": "Write",
        "input": {"file_path": f"{repo.path}/infra/a"},
        "cwd": str(repo.path),
        "actor": "someone",
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(request)))
    code = main(["policy", "eval", "--workspace", str(repo.path), "--sha", sha])
    capsys.readouterr()
    return code


def test_policy_eval_writes_a_policy_decision(tenant_repo, audited, monkeypatch, capsys) -> None:
    repo, sha = tenant_repo
    assert policy_eval(repo, sha, monkeypatch, capsys) == 0
    [event] = rows(audited)
    assert (event["kind"], event["tenant"], event["policy_sha"]) == ("policy_decision", "acme", sha)
    assert event["decision"] == "deny:readonly-repo" and event["tools"] == ["Write"]


def test_registry_list_and_lock_write_registry_resolve(tenant_repo, audited, capsys) -> None:
    repo, sha = tenant_repo
    assert main(["registry", "list", "--workspace", str(repo.path), "--sha", sha]) == 0
    assert main(["registry", "lock", "--workspace", str(repo.path), "--sha", sha]) == 0
    capsys.readouterr()
    assert [e["refs"]["command"] for e in rows(audited)] == ["registry list", "registry lock"]
    assert all(e["asset_set_sha"] == sha for e in rows(audited))


def test_eval_run_writes_one_model_call_per_run(tenant_repo, audited, tmp_path, capsys) -> None:
    repo, sha = tenant_repo
    args = ["eval", "run", "--workspace", str(repo.path), "--suite", "evals/routing/cases.yaml", "--sha", sha]
    answers = tmp_path / "answers.yaml"
    answers.write_text(yaml.safe_dump({f"case-{i}": "ask" for i in range(30)}))
    assert main([*args, "--provider", "fake", "--answers", str(answers)]) == 0
    capsys.readouterr()
    events = rows(audited)
    assert len(events) == 90 and {e["kind"] for e in events} == {"model_call"}
    assert {e["provider"] for e in events} == {"fake"} and "Resumen" not in json.dumps(events)
    assert main(["audit", "verify"]) == 0


def test_without_dsn_nothing_is_written(tenant_repo, dsns, monkeypatch, capsys) -> None:
    owner, _ = dsns
    monkeypatch.delenv("ORQUESTA_AUDIT_DSN", raising=False)
    repo, sha = tenant_repo
    assert policy_eval(repo, sha, monkeypatch, capsys) == 0
    assert rows(owner) == []


def test_dsn_with_an_open_key_exits_with_9(tenant_repo, dsns, key_file, monkeypatch, capsys) -> None:
    _, writer = dsns
    key_file.chmod(0o644)
    monkeypatch.setenv("ORQUESTA_AUDIT_DSN", writer)
    monkeypatch.setenv("ORQUESTA_AUDIT_KEY", str(key_file))
    repo, sha = tenant_repo
    assert policy_eval(repo, sha, monkeypatch, capsys) == 9
