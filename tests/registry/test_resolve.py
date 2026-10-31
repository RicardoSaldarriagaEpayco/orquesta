import pytest

from orquesta.errors import AssetError, ShaNotApproved
from orquesta.registry.resolve import resolve
from orquesta.workspace import Workspace


def head(repo) -> str:
    return repo.git("rev-parse", "HEAD")


def test_resolves_agents_and_skills_with_catalog_and_frontmatter(workspace) -> None:
    manifests = {m.id: m for m in resolve(Workspace(workspace.path), head(workspace))}
    assert sorted(manifests) == ["agent/reviewer", "skill/ship", "skill/vendored"]
    reviewer = manifests["agent/reviewer"]
    assert reviewer.tools == ["Read", "Grep"]
    assert reviewer.owner == "platform-team"
    assert reviewer.evals == ["routing"]
    assert reviewer.version == head(workspace)[:7]
    assert manifests["skill/ship"].path == ".claude/skills/ship"
    assert manifests["skill/ship"].disable_model_invocation is True
    assert manifests["skill/vendored"].license == "MIT"


def test_working_tree_changes_do_not_change_the_result(workspace) -> None:
    before = resolve(Workspace(workspace.path), head(workspace))
    (workspace.path / ".claude/skills/ship/reference.md").write_text("editado sin commit\n")
    assert resolve(Workspace(workspace.path), head(workspace)) == before


def test_a_new_commit_changes_only_that_asset_digest(workspace) -> None:
    sha = head(workspace)
    before = {m.id: m.digest for m in resolve(Workspace(workspace.path), sha)}
    new = workspace.commit({".claude/skills/ship/reference.md": "otro detalle\n"})
    workspace.approve(new)
    after = {m.id: m.digest for m in resolve(Workspace(workspace.path), new)}
    assert after["skill/ship"] != before["skill/ship"]
    assert after["agent/reviewer"] == before["agent/reviewer"]


def test_broken_frontmatter_names_asset_and_field(workspace) -> None:
    sha = workspace.commit({".claude/agents/reviewer.md": "---\nname: [sin cerrar\n---\n"})
    workspace.approve(sha)
    with pytest.raises(AssetError) as error:
        resolve(Workspace(workspace.path), sha)
    assert (error.value.asset_id, error.value.field, error.value.exit_code) == ("agent/reviewer", "frontmatter", 4)


def test_missing_frontmatter_is_an_asset_error(workspace) -> None:
    sha = workspace.commit({".claude/agents/reviewer.md": "sin frontmatter\n"})
    workspace.approve(sha)
    with pytest.raises(AssetError, match="frontmatter"):
        resolve(Workspace(workspace.path), sha)


def test_name_must_match_the_catalog_id(workspace) -> None:
    sha = workspace.commit({".claude/agents/reviewer.md": "---\nname: otro\ndescription: x\n---\n"})
    workspace.approve(sha)
    with pytest.raises(AssetError) as error:
        resolve(Workspace(workspace.path), sha)
    assert error.value.field == "name"


def test_asset_without_catalog_entry_fails(workspace) -> None:
    sha = workspace.commit({".claude/agents/nuevo.md": "---\nname: nuevo\ndescription: x\n---\n"})
    workspace.approve(sha)
    with pytest.raises(AssetError) as error:
        resolve(Workspace(workspace.path), sha)
    assert (error.value.asset_id, error.value.field) == ("agent/nuevo", "catalog")


def test_catalog_entry_without_asset_fails(workspace) -> None:
    workspace.git("rm", "-q", "-r", ".claude/skills/vendored")
    workspace.git("commit", "-q", "-m", "quita vendored")
    sha = head(workspace)
    workspace.approve(sha)
    with pytest.raises(AssetError) as error:
        resolve(Workspace(workspace.path), sha)
    assert error.value.asset_id == "skill/vendored"


def test_effects_without_disable_model_invocation_fail(workspace) -> None:
    sha = workspace.commit({".claude/skills/ship/SKILL.md": "---\nname: ship\ndescription: Sube cambios.\n---\n"})
    workspace.approve(sha)
    with pytest.raises(AssetError, match="disable-model-invocation"):
        resolve(Workspace(workspace.path), sha)


def test_source_pinned_to_a_tag_fails(workspace) -> None:
    catalog = (
        (workspace.path / "catalog.yaml")
        .read_text()
        .replace(
            "{url: https://example.com/vendor/kit, commit: 0123456789abcdef0123456789abcdef01234567}",
            "https://example.com/vendor/kit@v1",
        )
    )
    sha = workspace.commit({"catalog.yaml": catalog})
    workspace.approve(sha)
    with pytest.raises(AssetError) as error:
        resolve(Workspace(workspace.path), sha)
    assert error.value.asset_id == "skill/vendored"
    assert error.value.field == "source"
    assert "commit completo" in error.value.reason


def test_files_outside_the_asset_layout_are_ignored(workspace) -> None:
    sha = workspace.commit({".claude/settings.json": "{}", ".claude/skills/ship/nested/SKILL.md": "x"})
    workspace.approve(sha)
    assert len(resolve(Workspace(workspace.path), sha)) == 3


def test_unapproved_sha_exits_with_5(workspace) -> None:
    sha = workspace.commit({"README.md": "cambio sin aprobar\n"})
    with pytest.raises(ShaNotApproved):
        resolve(Workspace(workspace.path), sha)
