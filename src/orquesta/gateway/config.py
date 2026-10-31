from fnmatch import fnmatchcase

import yaml

from orquesta.gateway.gateway import Allowlist
from orquesta.policy.load import RulesUnreadable
from orquesta.workspace import Workspace


def load_models(workspace: Workspace, sha: str) -> tuple[Allowlist, str]:
    try:
        models = (yaml.safe_load(workspace.read(sha, "policy.yaml")) or {})["models"]
        allow = [str(pattern) for pattern in models["allow"]]
        default = str(models["default"])
    except (FileNotFoundError, yaml.YAMLError, KeyError, TypeError) as error:
        raise RulesUnreadable(f"models de policy.yaml: {type(error).__name__}: {error}") from error
    if not allow or not any(fnmatchcase(default, pattern) for pattern in allow):
        raise RulesUnreadable(f"models.default {default} no está en models.allow")
    return Allowlist(allow), default
