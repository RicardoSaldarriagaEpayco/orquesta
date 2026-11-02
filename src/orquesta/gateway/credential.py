import base64
import hashlib
import hmac
import json
import os
import stat
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from orquesta.errors import CredentialInvalid, KeyInsecure
from orquesta.gateway.gateway import Allowlist

MAX_TTL_S = 900
PREFIX = "oqe1"
DEFAULT_KEY = Path.home() / ".config" / "orquesta" / "gateway.key"


def key_path() -> Path:
    return Path(os.environ.get("ORQUESTA_GATEWAY_KEY", str(DEFAULT_KEY)))


def load_key(path: Path | None = None) -> bytes:
    path = path or key_path()
    try:
        info = path.stat()
    except OSError as error:
        raise KeyInsecure(str(path), "no existe o no se puede leer") from error
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise KeyInsecure(str(path), f"permisos {oct(info.st_mode & 0o777)}; debe ser 0600")
    key = path.read_bytes().strip()
    if len(key) < 32:
        raise KeyInsecure(str(path), "tiene menos de 32 bytes")
    return key


@dataclass(frozen=True)
class EpisodeClaims:
    run_id: str
    models: tuple[str, ...]
    budget_usd: float
    exp: int

    def to_dict(self) -> dict[str, object]:
        return {"run_id": self.run_id, "models": list(self.models), "budget_usd": self.budget_usd, "exp": self.exp}


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _mac(key: bytes, payload: str) -> str:
    return _b64(hmac.new(key, f"{PREFIX}.{payload}".encode(), hashlib.sha256).digest())


def issue(
    key: bytes,
    run_id: str,
    models: Sequence[str],
    budget_usd: float,
    ttl_s: int = MAX_TTL_S,
    now: Callable[[], float] = time.time,
) -> str:
    if not 0 < ttl_s <= MAX_TTL_S:
        raise ValueError(f"ttl_s debe estar entre 1 y {MAX_TTL_S}")
    if not run_id or not models or budget_usd < 0:
        raise ValueError("la credencial necesita run_id, modelos y presupuesto no negativo")
    claims = EpisodeClaims(run_id, tuple(models), float(budget_usd), int(now()) + ttl_s)
    payload = _b64(json.dumps(claims.to_dict(), sort_keys=True, separators=(",", ":")).encode())
    return f"{PREFIX}.{payload}.{_mac(key, payload)}"


def verify(key: bytes, token: str, run_id: str, now: Callable[[], float] = time.time) -> EpisodeClaims:
    prefix, _, rest = token.partition(".")
    payload, _, signature = rest.partition(".")
    if prefix != PREFIX or not payload or not signature:
        raise CredentialInvalid("formato")
    if not hmac.compare_digest(signature, _mac(key, payload)):
        raise CredentialInvalid("firma")
    try:
        raw = json.loads(_unb64(payload))
        claims = EpisodeClaims(raw["run_id"], tuple(raw["models"]), float(raw["budget_usd"]), int(raw["exp"]))
    except (ValueError, KeyError, TypeError) as error:
        raise CredentialInvalid("contenido") from error
    if claims.exp <= now():
        raise CredentialInvalid("vencida")
    if claims.exp - now() > MAX_TTL_S:
        raise CredentialInvalid("vigencia mayor a la permitida")
    if not hmac.compare_digest(claims.run_id, run_id):
        raise CredentialInvalid("de otra corrida")
    return claims


class EpisodeAllowlist(Allowlist):
    def __init__(self, tenant: Allowlist, claims: EpisodeClaims) -> None:
        super().__init__(claims.models)
        self.tenant = tenant

    def allows_provider(self, provider: str) -> bool:
        return super().allows_provider(provider) and self.tenant.allows_provider(provider)

    def allows(self, provider: str, model: str) -> bool:
        return super().allows(provider, model) and self.tenant.allows(provider, model)
