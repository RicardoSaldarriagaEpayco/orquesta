import hashlib
import hmac
import os
import secrets
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from orquesta.errors import Forbidden, KeyInsecure, Unauthenticated

ROLES = frozenset({"viewer", "operator", "approver"})
ANY_REPO = "*"
PREFIX = "oqt_"
DEFAULT_TOKENS = Path.home() / ".config" / "orquesta" / "api-tokens.yaml"


def tokens_path() -> Path:
    return Path(os.environ.get("ORQUESTA_API_TOKENS", str(DEFAULT_TOKENS)))


def _digest(token: str) -> str:
    return "sha256:" + hashlib.sha256(token.encode()).hexdigest()


def parse_grants(values: list[str]) -> dict[str, frozenset[str]]:
    grants: dict[str, frozenset[str]] = {}
    for value in values:
        repo, separator, roles = value.partition("=")
        names = frozenset(role.strip() for role in roles.split(",") if role.strip())
        if not separator or not repo or not names or not names <= ROLES:
            raise ValueError(f"permiso inválido {value!r}; usa <repo|*>=<rol>[,<rol>] con roles {sorted(ROLES)}")
        grants[repo] = grants.get(repo, frozenset()) | names
    return grants


@dataclass(frozen=True)
class Principal:
    actor: str
    grants: Mapping[str, frozenset[str]]

    def has(self, role: str, repo: str | None) -> bool:
        held = self.grants.get(ANY_REPO, frozenset())
        if repo is not None:
            held |= self.grants.get(repo, frozenset())
        return role in held or (role == "viewer" and bool(held))

    def require(self, role: str, repo: str | None) -> None:
        if not self.has(role, repo):
            raise Forbidden(self.actor, role, repo)


class TokenStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _check_private(self) -> None:
        info = self.path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise KeyInsecure(str(self.path), f"permisos {oct(info.st_mode & 0o777)}; debe ser 0600")

    def entries(self) -> list[dict]:
        try:
            self._check_private()
            raw = yaml.safe_load(self.path.read_text()) or {}
        except FileNotFoundError:
            return []
        except (OSError, yaml.YAMLError) as error:
            raise KeyInsecure(str(self.path), f"ilegible: {type(error).__name__}") from error
        if not isinstance(raw, dict) or not isinstance(raw.get("tokens", []), list):
            raise KeyInsecure(str(self.path), "formato inválido; se espera tokens: [...]")
        return list(raw.get("tokens", []))

    def authenticate(self, authorization: str | None) -> Principal:
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token.startswith(PREFIX):
            raise Unauthenticated()
        digest = _digest(token.strip())
        found = None
        for entry in self.entries():
            if hmac.compare_digest(str(entry.get("hash", "")), digest):
                found = entry
        if found is None:
            raise Unauthenticated()
        try:
            grants = parse_grants([f"{repo}={','.join(roles)}" for repo, roles in found["grants"].items()])
            return Principal(str(found["actor"]), grants)
        except (KeyError, TypeError, AttributeError, ValueError) as error:
            raise KeyInsecure(str(self.path), f"entrada de {found.get('actor')} inválida") from error

    def create(self, actor: str, grants: dict[str, frozenset[str]]) -> str:
        if not actor or not grants:
            raise ValueError("el token necesita actor y al menos un permiso")
        entries = self.entries()
        token = PREFIX + secrets.token_urlsafe(32)
        entries.append(
            {"actor": actor, "hash": _digest(token), "grants": {r: sorted(roles) for r, roles in grants.items()}}
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.unlink(missing_ok=True)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            yaml.safe_dump({"tokens": entries}, handle, sort_keys=False)
        os.replace(temporary, self.path)
        return token
