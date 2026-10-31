import os
import time
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
import yaml

from orquesta.audit.chain import AuditRecord, append
from orquesta.audit.key import load_key
from orquesta.gateway.gateway import ModelCall
from orquesta.workspace import Workspace


class AuditWriter:
    def __init__(self, dsn: str, key: bytes) -> None:
        self.dsn, self.key = dsn, key

    def write(self, record: AuditRecord) -> int:
        with psycopg.connect(self.dsn) as conn:
            return append(conn, self.key, record)


def writer_from_env() -> AuditWriter | None:
    dsn = os.environ.get("ORQUESTA_AUDIT_DSN", "")
    return AuditWriter(dsn, load_key()) if dsn else None


def tenant(workspace: Workspace, sha: str) -> str:
    try:
        return str((yaml.safe_load(workspace.read(sha, "workspace.yaml")) or {}).get("tenant") or "local")
    except (FileNotFoundError, yaml.YAMLError):
        return "local"


class Stopwatch:
    def __init__(self) -> None:
        self.started = time.monotonic()

    @property
    def ms(self) -> int:
        return max(0, round((time.monotonic() - self.started) * 1000))


@contextmanager
def stopwatch() -> Iterator[Stopwatch]:
    yield Stopwatch()


class ModelCallSink:
    def __init__(self, writer: AuditWriter | None, policy_sha: str, asset_set_sha: str) -> None:
        self.writer, self.policy_sha, self.asset_set_sha = writer, policy_sha, asset_set_sha
        self.events: list[ModelCall] = []

    def write(self, event: ModelCall) -> None:
        self.events.append(event)
        if self.writer is None:
            return
        self.writer.write(
            AuditRecord(
                **event.model_dump(exclude={"kind"}),
                kind="model_call",
                policy_sha=self.policy_sha,
                asset_set_sha=self.asset_set_sha,
            )
        )
