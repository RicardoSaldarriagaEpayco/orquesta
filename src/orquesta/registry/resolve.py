import hashlib
from datetime import date

import yaml
from pydantic import ValidationError

from orquesta.errors import AssetError
from orquesta.registry.models import AgentAssetManifest
from orquesta.workspace import Workspace

CATALOG = "catalog.yaml"
AGENTS = ".claude/agents/"
SKILLS = ".claude/skills/"
SOURCE_RULE = "debe ser workspace o {url, commit} con el commit completo de 40 caracteres"
FRONTMATTER_KEYS = {
    "description": "description",
    "tools": "tools",
    "disable-model-invocation": "disable_model_invocation",
}


def discover(workspace: Workspace, sha: str) -> dict[str, tuple[str, str]]:
    found: dict[str, tuple[str, str]] = {}
    for path in workspace.list(sha, ".claude"):
        parts = path.split("/")
        if path.startswith(AGENTS) and len(parts) == 3 and path.endswith(".md"):
            found[f"agent/{parts[2][:-3]}"] = (path, path)
        elif path.startswith(SKILLS) and len(parts) == 4 and parts[3] == "SKILL.md":
            found[f"skill/{parts[2]}"] = ("/".join(parts[:3]), path)
    return found


def frontmatter(asset_id: str, text: str) -> dict[str, object]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---" or "---" not in (line.strip() for line in lines[1:]):
        raise AssetError(asset_id, "frontmatter", "falta el bloque --- al inicio del archivo")
    end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    try:
        data = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as error:
        raise AssetError(asset_id, "frontmatter", f"YAML inválido: {error.problem}") from error
    if not isinstance(data, dict):
        raise AssetError(asset_id, "frontmatter", "no es un mapa de claves")
    return data


def catalog(workspace: Workspace, sha: str) -> dict[str, dict[str, object]]:
    try:
        data = yaml.safe_load(workspace.read(sha, CATALOG)) or {}
    except FileNotFoundError as error:
        raise AssetError("catalog", CATALOG, "no existe en el SHA") from error
    except yaml.YAMLError as error:
        raise AssetError("catalog", CATALOG, f"YAML inválido: {error.problem}") from error
    defaults = data.get("defaults") or {}
    entries: dict[str, dict[str, object]] = {}
    for entry in data.get("assets") or []:
        asset_id = str(entry.get("id"))
        if asset_id in entries:
            raise AssetError(asset_id, "id", "aparece más de una vez en catalog.yaml")
        entries[asset_id] = {**defaults, **entry}
    return entries


def digest(workspace: Workspace, sha: str, path: str) -> str:
    listing = workspace.tree(sha, path)
    return "sha256:" + hashlib.sha256(listing.encode()).hexdigest()


def resolve(workspace: Workspace, sha: str) -> list[AgentAssetManifest]:
    full = workspace.resolve(sha)
    assets = discover(workspace, full)
    entries = catalog(workspace, full)
    for asset_id in sorted(set(entries) - set(assets)):
        raise AssetError(asset_id, "path", "está en catalog.yaml y no existe en el SHA")
    manifests = []
    for asset_id, (path, document) in sorted(assets.items()):
        if asset_id not in entries:
            raise AssetError(asset_id, "catalog", "no tiene entrada en catalog.yaml")
        meta = frontmatter(asset_id, workspace.read(full, document))
        asset_type, name = asset_id.split("/", 1)
        if meta.get("name") != name:
            raise AssetError(asset_id, "name", f"el frontmatter dice {meta.get('name')!r}")
        fields = {target: meta[key] for key, target in FRONTMATTER_KEYS.items() if key in meta}
        if isinstance(fields.get("tools"), str):
            fields["tools"] = [tool.strip() for tool in str(fields["tools"]).split(",") if tool.strip()]
        candidate = {
            **{k: v for k, v in entries[asset_id].items() if v is not None},
            **fields,
            "id": asset_id,
            "type": asset_type,
            "name": name,
            "version": full[:7],
            "sha": full,
            "path": path,
            "digest": digest(workspace, full, path),
        }
        try:
            manifests.append(AgentAssetManifest.model_validate(candidate))
        except ValidationError as error:
            first = error.errors()[0]
            if first["loc"] and first["loc"][0] == "source":
                raise AssetError(asset_id, "source", SOURCE_RULE) from error
            field = ".".join(str(part) for part in first["loc"]) or "manifest"
            raise AssetError(asset_id, field, first["msg"]) from error
    return manifests


def active(manifests: list[AgentAssetManifest], today: date) -> list[AgentAssetManifest]:
    return [m for m in manifests if m.expires is None or m.expires >= today]
