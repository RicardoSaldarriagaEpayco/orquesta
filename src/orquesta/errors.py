import json
import sys
from typing import TextIO


class OrquestaError(Exception):
    exit_code = 1

    def fields(self) -> dict[str, object]:
        return {}

    def to_dict(self) -> dict[str, object]:
        return {"error": type(self).__name__, **self.fields(), "message": str(self)}

    def report(self, as_json: bool, stream: TextIO | None = None) -> None:
        line = json.dumps(self.to_dict(), ensure_ascii=False) if as_json else f"{type(self).__name__}: {self}"
        print(line, file=stream or sys.stderr)


class IdentityMissing(OrquestaError):
    def __init__(self) -> None:
        super().__init__("sin identidad: define ORQUESTA_ACTOR o inicia sesión con gh auth login")


class AssetError(OrquestaError):
    exit_code = 4

    def __init__(self, asset_id: str, field: str, reason: str) -> None:
        self.asset_id, self.field, self.reason = asset_id, field, reason
        super().__init__(f"{asset_id}: {field}: {reason}")

    def fields(self) -> dict[str, object]:
        return {"asset_id": self.asset_id, "field": self.field, "reason": self.reason}


class ShaNotApproved(OrquestaError):
    exit_code = 5

    def __init__(self, sha: str, ref: str) -> None:
        self.sha, self.ref = sha, ref
        super().__init__(f"{sha} no es un commit alcanzable desde {ref}")

    def fields(self) -> dict[str, object]:
        return {"sha": self.sha, "ref": self.ref}


class AuditChainBroken(OrquestaError):
    exit_code = 7

    def __init__(self, seq: int) -> None:
        self.seq = seq
        super().__init__(f"la cadena de auditoría se rompe en seq {seq}")

    def fields(self) -> dict[str, object]:
        return {"seq": self.seq}


class ModelNotAllowed(OrquestaError):
    def __init__(self, provider: str, model: str) -> None:
        self.provider, self.model = provider, model
        super().__init__(f"{provider}/{model} no está en la allowlist del tenant")

    def fields(self) -> dict[str, object]:
        return {"provider": self.provider, "model": self.model}


class ProviderNotAllowed(OrquestaError):
    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(f"el proveedor {provider} no está en la allowlist del tenant")

    def fields(self) -> dict[str, object]:
        return {"provider": self.provider}


class ProviderError(OrquestaError):
    def __init__(self, provider: str, reason: str) -> None:
        self.provider, self.reason = provider, reason
        super().__init__(f"{provider}: {reason}")

    def fields(self) -> dict[str, object]:
        return {"provider": self.provider, "reason": self.reason}


class SuiteInvalid(OrquestaError):
    exit_code = 8

    def __init__(self, suite: str, reason: str) -> None:
        self.suite, self.reason = suite, reason
        super().__init__(f"{suite}: {reason}")

    def fields(self) -> dict[str, object]:
        return {"suite": self.suite, "reason": self.reason}


class AuditKeyInsecure(OrquestaError):
    exit_code = 9

    def __init__(self, path: str, reason: str) -> None:
        self.path, self.reason = path, reason
        super().__init__(f"llave de auditoría {path}: {reason}")

    def fields(self) -> dict[str, object]:
        return {"path": self.path, "reason": self.reason}


class AuditUnavailable(OrquestaError):
    exit_code = 9

    def __init__(self, reason: str) -> None:
        super().__init__(f"auditoría no disponible: {reason}")


class GraphStoreUnavailable(OrquestaError):
    exit_code = 12

    def __init__(self, reason: str) -> None:
        super().__init__(f"estado de grafos no disponible: {reason}")


class TicketError(OrquestaError):
    exit_code = 13

    def __init__(self, ticket: str, reason: str) -> None:
        self.ticket, self.reason = ticket, reason
        super().__init__(f"{ticket}: {reason}")

    def fields(self) -> dict[str, object]:
        return {"ticket": self.ticket, "reason": self.reason}


class CredentialInvalid(OrquestaError):
    exit_code = 14

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"credencial de episodio inválida: {reason}")

    def fields(self) -> dict[str, object]:
        return {"reason": self.reason}


class Unauthenticated(OrquestaError):
    exit_code = 15

    def __init__(self) -> None:
        super().__init__("token ausente o no reconocido")


class Forbidden(OrquestaError):
    exit_code = 15

    def __init__(self, actor: str, role: str, repo: str | None) -> None:
        self.actor, self.role, self.repo = actor, role, repo
        super().__init__(f"{actor} no tiene el rol {role} en {repo or 'el tenant'}")

    def fields(self) -> dict[str, object]:
        return {"actor": self.actor, "role": self.role, "repo": self.repo}


class BudgetExceeded(OrquestaError):
    exit_code = 10

    def __init__(self, limit_usd: float, spent_usd: float) -> None:
        self.limit_usd, self.spent_usd = limit_usd, spent_usd
        super().__init__(f"presupuesto agotado: {spent_usd:.6f} de {limit_usd:.6f} USD")

    def fields(self) -> dict[str, object]:
        return {"limit_usd": self.limit_usd, "spent_usd": self.spent_usd}


class KeyInsecure(OrquestaError):
    exit_code = 9

    def __init__(self, path: str, reason: str) -> None:
        self.path, self.reason = path, reason
        super().__init__(f"llave {path}: {reason}")

    def fields(self) -> dict[str, object]:
        return {"path": self.path, "reason": self.reason}


class ReceiptInvalid(OrquestaError):
    exit_code = 11

    def __init__(self, sha: str, reason: str) -> None:
        self.sha, self.reason = sha, reason
        super().__init__(f"recibo de {sha[:12]}: {reason}")

    def fields(self) -> dict[str, object]:
        return {"sha": self.sha, "reason": self.reason}
