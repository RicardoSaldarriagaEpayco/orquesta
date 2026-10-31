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
