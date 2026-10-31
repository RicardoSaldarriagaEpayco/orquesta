import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from orquesta.registry.models import AgentAssetManifest
from orquesta.registry.resolve import resolve
from orquesta.workspace import Workspace

CONTRACT = json.loads((Path(__file__).parents[2] / "contracts" / "agent-asset-manifest.schema.json").read_text())

VALID = {
    "id": "skill/ship",
    "type": "skill",
    "name": "ship",
    "version": "abcdef0",
    "sha": "a" * 40,
    "path": ".claude/skills/ship",
    "digest": "sha256:" + "b" * 64,
    "owner": "platform-team",
    "source": "workspace",
    "classification": "internal",
    "egress": [],
    "external_effects": [],
    "evals": [],
    "approvals": [],
}


def test_model_fields_match_the_contract() -> None:
    schema = AgentAssetManifest.model_json_schema()
    assert set(schema["properties"]) == set(CONTRACT["properties"])
    assert set(schema["required"]) == set(CONTRACT["required"])


def test_resolved_manifests_validate_against_the_contract(workspace) -> None:
    for manifest in resolve(Workspace(workspace.path), workspace.git("rev-parse", "HEAD")):
        jsonschema.validate(manifest.to_json(), CONTRACT)


@pytest.mark.parametrize(
    "change",
    [
        {"path": ".claude/skills/../secrets"},
        {"path": "src/elsewhere"},
        {"source": {"url": "https://example.com/kit", "commit": "a" * 40}},
        {"external_effects": ["push"]},
        {"external_effects": ["deploy"]},
        {"evals": ["routing", "routing"]},
        {"extra": "campo"},
    ],
)
def test_contract_and_model_reject_the_same_manifests(change: dict[str, object]) -> None:
    candidate = {**VALID, **change}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(candidate, CONTRACT)
    with pytest.raises(ValidationError):
        AgentAssetManifest.model_validate(candidate)


def test_model_also_requires_id_to_match_type_and_name() -> None:
    with pytest.raises(ValidationError, match="no coincide"):
        AgentAssetManifest.model_validate({**VALID, "id": "agent/ship"})


def test_valid_manifest_passes_both() -> None:
    jsonschema.validate(VALID, CONTRACT)
    assert AgentAssetManifest.model_validate(VALID).to_json() == VALID
