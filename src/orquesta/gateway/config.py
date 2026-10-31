from dataclasses import dataclass, field
from fnmatch import fnmatchcase

import yaml

from orquesta.gateway.gateway import Allowlist, Budget
from orquesta.policy.load import RulesUnreadable
from orquesta.workspace import Workspace


@dataclass(frozen=True)
class ModelsConfig:
    allowlist: Allowlist
    default: str
    budget_usd: float | None = None
    prices: dict[str, tuple[float, float]] = field(default_factory=dict)

    def budget(self) -> Budget:
        return Budget(self.budget_usd)


def load_models(workspace: Workspace, sha: str) -> ModelsConfig:
    try:
        models = (yaml.safe_load(workspace.read(sha, "policy.yaml")) or {})["models"]
        allow = [str(pattern) for pattern in models["allow"]]
        default = str(models["default"])
        budget = models.get("budget_usd")
        budget = None if budget is None else float(budget)
        prices = {str(m): (float(p[0]), float(p[1])) for m, p in (models.get("prices") or {}).items()}
    except (FileNotFoundError, yaml.YAMLError, KeyError, TypeError, ValueError, IndexError) as error:
        raise RulesUnreadable(f"models de policy.yaml: {type(error).__name__}: {error}") from error
    if not allow or not any(fnmatchcase(default, pattern) for pattern in allow):
        raise RulesUnreadable(f"models.default {default} no está en models.allow")
    if budget is not None and budget < 0:
        raise RulesUnreadable("models.budget_usd no puede ser negativo")
    return ModelsConfig(Allowlist(allow), default, budget, prices)
