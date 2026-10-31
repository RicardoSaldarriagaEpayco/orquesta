import hashlib
import hmac
import json
from decimal import Decimal
from typing import Literal

from psycopg import Connection
from pydantic import BaseModel, Field

from orquesta.audit.redact import redact, redact_refs
from orquesta.errors import AuditChainBroken

GENESIS = bytes(32)
LOCK_ID = 7_401_202_610
Kind = Literal["model_call", "policy_decision", "registry_resolve", "promotion", "eval_run"]
COLUMNS = (
    "actor", "tenant", "kind", "policy_sha", "asset_set_sha", "provider", "model", "tools", "decision",
    "latency_ms", "cost_usd", "refs",
)  # fmt: skip


class AuditRecord(BaseModel):
    actor: str = Field(min_length=1)
    tenant: str = Field(pattern=r"^[a-z0-9-]+$")
    kind: Kind
    policy_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    asset_set_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    provider: str | None = None
    model: str | None = None
    tools: list[str] = Field(default_factory=list)
    decision: str = Field(max_length=512)
    latency_ms: int = Field(ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    refs: dict[str, str] = Field(default_factory=dict)

    def redacted(self) -> "AuditRecord":
        return self.model_copy(update={"decision": redact(self.decision)[:512], "refs": redact_refs(self.refs)})


def canon(values: dict[str, object]) -> bytes:
    normalized = {
        key: (float(value) if isinstance(value, Decimal) else value) for key, value in values.items() if key in COLUMNS
    }
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def mac(key: bytes, prev: bytes, values: dict[str, object]) -> bytes:
    return hmac.new(key, prev + canon(values), hashlib.sha256).digest()


def append(conn: Connection, key: bytes, record: AuditRecord) -> int:
    values = record.redacted().model_dump()
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
        last = conn.execute("SELECT mac FROM audit_events ORDER BY seq DESC LIMIT 1").fetchone()
        prev = bytes(last[0]) if last else GENESIS
        row = conn.execute(
            f"INSERT INTO audit_events ({', '.join(COLUMNS)}, prev_mac, mac) "
            f"VALUES ({', '.join(['%s'] * len(COLUMNS))}, %s, %s) RETURNING seq",
            (*[json.dumps(values[c]) if c == "refs" else values[c] for c in COLUMNS], prev, mac(key, prev, values)),
        ).fetchone()
    return int(row[0])


def verify(conn: Connection, key: bytes) -> int:
    prev, last_seq, count = GENESIS, 0, 0
    cursor = conn.execute(f"SELECT seq, {', '.join(COLUMNS)}, prev_mac, mac FROM audit_events ORDER BY seq")
    for row in cursor:
        seq = row[0]
        values = dict(zip(COLUMNS, row[1:-2], strict=True))
        stored_prev, stored_mac = bytes(row[-2]), bytes(row[-1])
        if seq <= last_seq:
            raise AuditChainBroken(seq)
        if stored_prev != prev or not hmac.compare_digest(stored_mac, mac(key, stored_prev, values)):
            raise AuditChainBroken(seq)
        prev, last_seq, count = stored_mac, seq, count + 1
    return count
