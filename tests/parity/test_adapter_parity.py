import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from orquesta.cli import main

from ..conftest import GIT_ENV, Repo

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "adapters" / "claude-code" / "policy-hook.sh"
ENGINE = Path(sys.executable).parent / "orquesta"
POLICY = """version: 1
protected_branches: [main]
local_branches: ['qa/*']
worktree_root: platform/
spec_root: platform/specs/
ai_attribution_patterns: ['generated with \\[?claude code']
pr_requires_receipt: true
"""
WORKSPACE = """version: 1
tenant: example
repos:
  - {name: shop-plugin, write: true}
  - {name: infra-gitops, write: false}
"""


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    base = tmp_path_factory.mktemp("parity")
    workspace = Repo(base / "platform")
    workspace.approve(workspace.commit({"policy.yaml": POLICY, "workspace.yaml": WORKSPACE, ".gitignore": "/*/\n"}))
    for name in ("shop-plugin", "infra-gitops"):
        Repo(base / "platform" / name).commit({"README.md": name})
    return base / "platform"


def cases(root: Path) -> list[tuple[str, dict, str | None]]:
    product, readonly = root / "shop-plugin", root / "infra-gitops"
    return [
        (
            "escritura en solo lectura",
            {"tool_name": "Write", "tool_input": {"file_path": f"{readonly}/a"}, "cwd": str(root)},
            "deny",
        ),
        (
            "escritura en producto",
            {"tool_name": "Write", "tool_input": {"file_path": f"{product}/src/a.py"}, "cwd": str(product)},
            None,
        ),
        (
            "rm en solo lectura",
            {"tool_name": "Bash", "tool_input": {"command": f"rm -rf {readonly}/x"}, "cwd": str(root)},
            "deny",
        ),
        (
            "lectura en solo lectura",
            {"tool_name": "Bash", "tool_input": {"command": "git log -3"}, "cwd": str(readonly)},
            None,
        ),
        (
            "spec-kit en producto",
            {"tool_name": "Skill", "tool_input": {"skill": "speckit-plan"}, "cwd": str(product)},
            "deny",
        ),
        ("worktree en producto", {"tool_name": "EnterWorktree", "tool_input": {}, "cwd": str(product)}, "deny"),
        (
            "push a main",
            {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}, "cwd": str(product)},
            "deny",
        ),
        (
            "merge propio",
            {"tool_name": "Bash", "tool_input": {"command": "gh pr merge 3"}, "cwd": str(product)},
            "deny",
        ),
        (
            "herramienta desconocida",
            {"tool_name": "WebFetch", "tool_input": {"url": "https://x"}, "cwd": str(root)},
            "deny",
        ),
    ]


def verdict(output: str) -> str | None:
    return json.loads(output)["hookSpecificOutput"]["permissionDecision"] if output.strip() else None


def engine_verdict(root: Path, payload: dict, monkeypatch, capsys) -> str | None:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    sha = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "origin/main"], capture_output=True, text=True
    ).stdout.strip()
    assert main(["policy", "eval", "--hook", "--workspace", str(root), "--sha", sha]) == 0
    return verdict(capsys.readouterr().out)


def adapter_verdict(root: Path, payload: dict, **extra: str) -> str | None:
    env = {
        **os.environ,
        **GIT_ENV,
        "ORQUESTA_WORKSPACE": str(root),
        "ORQUESTA_BIN": str(ENGINE),
        "ORQUESTA_ACTOR": "someone",
        **extra,
    }
    result = subprocess.run(
        ["bash", str(ADAPTER)], input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=60
    )
    return verdict(result.stdout)


def test_engine_and_adapter_agree_on_every_case(tree, monkeypatch, capsys) -> None:
    monkeypatch.setenv("ORQUESTA_ACTOR", "someone")
    for name, payload, expected in cases(tree):
        direct = engine_verdict(tree, payload, monkeypatch, capsys)
        through_hook = adapter_verdict(tree, payload)
        assert (name, direct) == (name, expected)
        assert (name, through_hook) == (name, direct)


@pytest.mark.parametrize(
    "extra",
    [{"ORQUESTA_BIN": "/no/existe/orquesta"}, {"ORQUESTA_WORKSPACE": ""}, {"ORQUESTA_APPROVED_REF": "no-existe"}],
)
def test_adapter_fails_closed(tree, extra) -> None:
    payload = {"tool_name": "Write", "tool_input": {"file_path": f"{tree}/shop-plugin/a"}, "cwd": str(tree)}
    assert adapter_verdict(tree, payload, **extra) == "deny"
