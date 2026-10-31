import json
from datetime import date

import pytest

from orquesta.cli import main
from orquesta.registry.lock import ApprovedSet, LockMismatch, StalePromotion, lock, verify
from orquesta.registry.resolve import resolve
from orquesta.workspace import Workspace


def head(repo) -> str:
    return repo.git("rev-parse", "HEAD")


def test_lock_maps_each_asset_to_its_digest(workspace) -> None:
    sha = head(workspace)
    candidate = lock(Workspace(workspace.path), sha)
    assert candidate.sha == sha and candidate.state == "candidate"
    assert candidate.lock == {m.id: m.digest for m in resolve(Workspace(workspace.path), sha)}


def test_expired_assets_are_left_out_of_the_lock(workspace) -> None:
    catalog = (
        (workspace.path / "catalog.yaml")
        .read_text()
        .replace("  - id: agent/reviewer\n", "  - id: agent/reviewer\n    expires: 2026-01-01\n")
    )
    sha = workspace.commit({"catalog.yaml": catalog})
    workspace.approve(sha)
    assert "agent/reviewer" not in lock(Workspace(workspace.path), sha, today=date(2026, 6, 1)).lock
    assert "agent/reviewer" in lock(Workspace(workspace.path), sha, today=date(2025, 6, 1)).lock


def test_verify_accepts_an_untouched_lock(workspace, tmp_path) -> None:
    lock_file = tmp_path / "lock.json"
    lock_file.write_text(json.dumps(lock(Workspace(workspace.path), head(workspace)).to_json()))
    assert verify(Workspace(workspace.path), lock_file).sha == head(workspace)


def test_verify_with_a_changed_digest_exits_with_6(workspace, tmp_path) -> None:
    data = lock(Workspace(workspace.path), head(workspace)).to_json()
    data["lock"]["skill/ship"] = "sha256:" + "0" * 64
    lock_file = tmp_path / "lock.json"
    lock_file.write_text(json.dumps(data))
    with pytest.raises(LockMismatch) as error:
        verify(Workspace(workspace.path), lock_file)
    assert error.value.exit_code == 6
    assert list(error.value.differences) == ["skill/ship"]


def test_cli_lock_and_verify(workspace, tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("ORQUESTA_ACTOR", "someone")
    assert main(["registry", "lock", "--workspace", str(workspace.path), "--sha", head(workspace)]) == 0
    data = json.loads(capsys.readouterr().out)
    data["lock"]["agent/reviewer"] = "sha256:" + "f" * 64
    lock_file = tmp_path / "lock.json"
    lock_file.write_text(json.dumps(data))
    assert main(["registry", "verify", "--workspace", str(workspace.path), "--lock", str(lock_file), "--json"]) == 6
    assert json.loads(capsys.readouterr().err)["error"] == "LockMismatch"


def test_cli_list_reports_asset_error_with_4(workspace, monkeypatch, capsys) -> None:
    monkeypatch.setenv("ORQUESTA_ACTOR", "someone")
    sha = workspace.commit({".claude/agents/reviewer.md": "sin frontmatter\n"})
    workspace.approve(sha)
    assert main(["registry", "list", "--workspace", str(workspace.path), "--sha", sha, "--json"]) == 4
    assert json.loads(capsys.readouterr().err)["asset_id"] == "agent/reviewer"


def test_cli_list_unapproved_sha_exits_with_5(workspace, monkeypatch) -> None:
    monkeypatch.setenv("ORQUESTA_ACTOR", "someone")
    sha = workspace.commit({"README.md": "sin aprobar\n"})
    assert main(["registry", "list", "--workspace", str(workspace.path), "--sha", sha]) == 5


def candidate(sha: str) -> ApprovedSet:
    return ApprovedSet(sha=sha, lock={"agent/reviewer": "sha256:" + "1" * 64})


def test_first_promotion_expects_no_current_set() -> None:
    approved = candidate("a" * 40).approve(None, None, by="lead")
    assert approved.state == "approved" and approved.previous is None and approved.approved_by == "lead"


def test_promotion_supersedes_the_current_set_and_rollback_restores_it() -> None:
    first = candidate("a" * 40).approve(None, None, by="lead")
    second = candidate("b" * 40).approve(first, "a" * 40, by="lead")
    assert second.previous is not None and second.previous.state == "superseded"
    restored = second.rollback()
    assert restored.sha == "a" * 40 and restored.state == "approved"


def test_promotion_with_a_stale_expected_sha_is_rejected() -> None:
    current = candidate("c" * 40).approve(None, None, by="lead")
    with pytest.raises(StalePromotion):
        candidate("b" * 40).approve(current, "a" * 40, by="lead")


def test_only_candidates_are_approved_and_rollback_needs_a_previous_set() -> None:
    approved = candidate("a" * 40).approve(None, None, by="lead")
    with pytest.raises(ValueError):
        approved.approve(None, None, by="lead")
    with pytest.raises(ValueError):
        approved.rollback()
