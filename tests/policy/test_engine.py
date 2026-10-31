import io
import json

import pytest

from orquesta.cli import main

POLICY = """version: 1
protected_branches: [main]
worktree_root: workspace/
spec_root: workspace/specs/
ai_attribution_patterns: ['generated with \\[?claude code']
pr_requires_receipt: true
"""
WORKSPACE = """version: 1
repos:
  - name: infra
    write: false
  - name: shop
    write: true
"""


@pytest.fixture
def tenant(repo, monkeypatch):
    monkeypatch.setenv("ORQUESTA_ACTOR", "someone")
    sha = repo.commit({"policy.yaml": POLICY, "workspace.yaml": WORKSPACE})
    repo.approve(sha)
    return repo, sha


def run(monkeypatch, capsys, args: list[str], stdin: str) -> tuple[int, str, str]:
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    code = main(["policy", "eval", *args])
    out = capsys.readouterr()
    return code, out.out, out.err


def request(path: str, tool: str = "Write", cwd: str = "/") -> str:
    return json.dumps(
        {"entrypoint": "claude-wsl", "tool": tool, "input": {"file_path": path}, "cwd": cwd, "actor": "someone"}
    )


def test_denies_a_write_in_a_readonly_repo_from_the_approved_sha(tenant, monkeypatch, capsys) -> None:
    repo, sha = tenant
    code, out, _ = run(
        monkeypatch, capsys, ["--workspace", str(repo.path), "--sha", sha], request(f"{repo.path}/infra/a")
    )
    decision = json.loads(out)
    assert code == 0
    assert (decision["verdict"], decision["rule_id"], decision["policy_sha"]) == ("deny", "readonly-repo", sha)


def test_allows_a_write_elsewhere(tenant, monkeypatch, capsys) -> None:
    repo, sha = tenant
    code, out, _ = run(
        monkeypatch, capsys, ["--workspace", str(repo.path), "--sha", sha], request(f"{repo.path}/shop/a")
    )
    assert code == 0 and json.loads(out)["verdict"] == "allow"


def test_working_tree_rules_are_ignored(tenant, monkeypatch, capsys) -> None:
    repo, sha = tenant
    (repo.path / "workspace.yaml").write_text("version: 1\nrepos: []\n")
    code, out, _ = run(
        monkeypatch, capsys, ["--workspace", str(repo.path), "--sha", sha], request(f"{repo.path}/infra/a")
    )
    assert json.loads(out)["rule_id"] == "readonly-repo"


@pytest.mark.parametrize("stdin", ["{no es json", "[]", '{"tool": "Bash"}', ""])
def test_unreadable_request_exits_with_2(tenant, monkeypatch, capsys, stdin: str) -> None:
    repo, sha = tenant
    code, out, err = run(monkeypatch, capsys, ["--workspace", str(repo.path), "--sha", sha, "--json"], stdin)
    assert code == 2 and out == ""
    assert json.loads(err)["error"] == "RequestUnreadable"


def test_unapproved_sha_exits_with_3(tenant, monkeypatch, capsys) -> None:
    repo, _ = tenant
    later = repo.commit({"README.md": "sin aprobar\n"})
    code, _, err = run(monkeypatch, capsys, ["--workspace", str(repo.path), "--sha", later], request("/x"))
    assert code == 3 and "RulesUnreadable" in err


@pytest.mark.parametrize(
    "files",
    [
        {"policy.yaml": "protected_branches: [main\n"},
        {"policy.yaml": "version: 1\n"},
        {"workspace.yaml": "version: 1\n"},
    ],
)
def test_unreadable_rules_exit_with_3(repo, monkeypatch, capsys, files: dict[str, str]) -> None:
    monkeypatch.setenv("ORQUESTA_ACTOR", "someone")
    sha = repo.commit({"policy.yaml": POLICY, "workspace.yaml": WORKSPACE, **files})
    repo.approve(sha)
    code, _, _ = run(monkeypatch, capsys, ["--workspace", str(repo.path), "--sha", sha], request("/x"))
    assert code == 3


def test_missing_rules_exit_with_3(repo, monkeypatch, capsys) -> None:
    monkeypatch.setenv("ORQUESTA_ACTOR", "someone")
    sha = repo.commit({"README.md": "sin reglas\n"})
    repo.approve(sha)
    code, _, _ = run(monkeypatch, capsys, ["--workspace", str(repo.path), "--sha", sha], request("/x"))
    assert code == 3


def test_unc_paths_are_normalized(tenant, monkeypatch, capsys) -> None:
    repo, sha = tenant
    unc = "\\\\wsl.localhost\\Ubuntu" + str(repo.path).replace("/", "\\") + "\\infra\\a"
    code, out, _ = run(monkeypatch, capsys, ["--workspace", str(repo.path), "--sha", sha], request(unc))
    assert json.loads(out)["rule_id"] == "readonly-repo"


FIXTURE = """environment:
  workspace_name: ws
  repos:
    - {path: "{root}", kind: workspace, branch: main}
cases:
  - name: escritura en solo lectura
    request: {tool: Write, input: {file_path: "{root}/infra/a"}, cwd: "{root}"}
    expect: {verdict: deny, rule_id: readonly-repo}
  - name: escritura permitida
    request: {tool: Write, input: {file_path: "{root}/shop/a"}, cwd: "{root}"}
    expect: {verdict: EXPECTED, rule_id: none}
"""


@pytest.mark.parametrize(("expected", "code"), [("allow", 0), ("deny", 1)])
def test_policy_test_runs_a_tenant_fixture_with_the_sha_rules(tenant, tmp_path, capsys, expected, code) -> None:
    repo, sha = tenant
    fixture = tmp_path / "fixtures.yaml"
    fixture.write_text(FIXTURE.replace("EXPECTED", expected))
    args = ["policy", "test", "--workspace", str(repo.path), "--sha", sha, "--fixtures", str(fixture)]
    assert main(args) == code
    assert ("2 de 2" if code == 0 else "1 de 2") in capsys.readouterr().out


def test_a_linked_worktree_uses_the_main_checkout_as_root(tenant, tmp_path, monkeypatch, capsys) -> None:
    repo, sha = tenant
    linked = tmp_path / "linked"
    repo.git("worktree", "add", "-q", "--detach", str(linked), sha)
    target = f"{repo.path}/infra/a"
    code, out, _ = run(monkeypatch, capsys, ["--workspace", str(linked), "--sha", sha], request(target))
    assert code == 0 and json.loads(out)["rule_id"] == "readonly-repo"


def test_hook_mode_speaks_pre_tool_use(tenant, monkeypatch, capsys) -> None:
    repo, sha = tenant
    payload = {"tool_name": "Write", "tool_input": {"file_path": f"{repo.path}/infra/a"}, "cwd": str(repo.path)}
    code, out, _ = run(
        monkeypatch, capsys, ["--workspace", str(repo.path), "--sha", sha, "--hook"], json.dumps(payload)
    )
    decision = json.loads(out)["hookSpecificOutput"]
    assert (
        code == 0
        and decision["permissionDecision"] == "deny"
        and "[readonly-repo]" in decision["permissionDecisionReason"]
    )
    payload["tool_input"]["file_path"] = f"{repo.path}/shop/a"
    code, out, _ = run(
        monkeypatch, capsys, ["--workspace", str(repo.path), "--sha", sha, "--hook"], json.dumps(payload)
    )
    assert code == 0 and out == ""


def test_hook_mode_with_unreadable_payload_exits_with_2(tenant, monkeypatch, capsys) -> None:
    repo, sha = tenant
    code, out, _ = run(monkeypatch, capsys, ["--workspace", str(repo.path), "--sha", sha, "--hook"], "[1, 2]")
    assert code == 2 and out == ""
