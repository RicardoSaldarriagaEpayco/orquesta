import pytest

from orquesta.errors import ShaNotApproved
from orquesta.workspace import Workspace


def test_reads_the_commit_not_the_working_tree(repo) -> None:
    sha = repo.commit({"policy.yaml": "version: 1\n"})
    repo.approve(sha)
    (repo.path / "policy.yaml").write_text("version: 2\n")
    assert Workspace(repo.path).read(sha, "policy.yaml") == "version: 1\n"


def test_unknown_sha_exits_with_5(repo) -> None:
    repo.approve(repo.commit({"a.txt": "a"}))
    with pytest.raises(ShaNotApproved) as error:
        Workspace(repo.path).read("0" * 40, "a.txt")
    assert error.value.exit_code == 5


def test_commit_not_reachable_from_approved_ref_is_rejected(repo) -> None:
    approved = repo.commit({"a.txt": "a"})
    repo.approve(approved)
    later = repo.commit({"a.txt": "b"})
    with pytest.raises(ShaNotApproved):
        Workspace(repo.path).read(later, "a.txt")


def test_option_like_sha_is_rejected(repo) -> None:
    repo.approve(repo.commit({"a.txt": "a"}))
    with pytest.raises(ShaNotApproved):
        Workspace(repo.path).resolve("--all")


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", "..\\x", ""])
def test_paths_outside_the_workspace_are_rejected(repo, path: str) -> None:
    sha = repo.commit({"a.txt": "a"})
    repo.approve(sha)
    with pytest.raises(ValueError):
        Workspace(repo.path).read(sha, path)


def test_missing_file_is_reported(repo) -> None:
    sha = repo.commit({"a.txt": "a"})
    repo.approve(sha)
    with pytest.raises(FileNotFoundError):
        Workspace(repo.path).read(sha, "b.txt")


def test_lists_files_under_a_prefix(repo) -> None:
    sha = repo.commit({".claude/agents/x.md": "x", ".claude/skills/y/SKILL.md": "y", "other.txt": "o"})
    repo.approve(sha)
    assert Workspace(repo.path).list(sha, ".claude") == [".claude/agents/x.md", ".claude/skills/y/SKILL.md"]
