import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import Field

from orquesta.errors import OrquestaError
from orquesta.registry.models import HEX40, Strict
from orquesta.registry.resolve import active, resolve
from orquesta.workspace import Workspace

State = Literal["candidate", "approved", "superseded"]


class LockMismatch(OrquestaError):
    exit_code = 6

    def __init__(self, differences: dict[str, dict[str, str | None]]) -> None:
        self.differences = differences
        super().__init__(f"{len(differences)} activos difieren del lock")

    def fields(self) -> dict[str, object]:
        return {"differences": self.differences}


class StalePromotion(OrquestaError):
    def __init__(self, expected: str | None, current: str | None) -> None:
        self.expected, self.current = expected, current
        super().__init__(f"se esperaba el conjunto vigente {expected} y el vigente es {current}")

    def fields(self) -> dict[str, object]:
        return {"expected": self.expected, "current": self.current}


class ApprovedSet(Strict):
    sha: str = Field(pattern=HEX40)
    lock: dict[str, str]
    state: State = "candidate"
    previous: "ApprovedSet | None" = None
    approved_by: str | None = None
    approved_at: datetime | None = None

    def to_json(self) -> dict[str, object]:
        return self.model_dump(mode="json")

    def approve(self, current: Self | None, expected_sha: str | None, by: str, at: datetime | None = None) -> Self:
        if self.state != "candidate":
            raise ValueError(f"solo un candidato se aprueba; este está {self.state}")
        current_sha = current.sha if current else None
        if current_sha != expected_sha:
            raise StalePromotion(expected_sha, current_sha)
        previous = current.model_copy(update={"state": "superseded"}) if current else None
        return self.model_copy(
            update={
                "state": "approved",
                "previous": previous,
                "approved_by": by,
                "approved_at": at or datetime.now(UTC),
            }
        )

    def rollback(self) -> Self:
        if self.state != "approved" or self.previous is None:
            raise ValueError("no hay un conjunto anterior al que volver")
        return self.previous.model_copy(update={"state": "approved"})


def lock(workspace: Workspace, sha: str, today: date | None = None) -> ApprovedSet:
    manifests = active(resolve(workspace, sha), today or date.today())
    full = workspace.resolve(sha)
    return ApprovedSet(sha=full, lock={m.id: m.digest for m in manifests})


def verify(workspace: Workspace, lock_file: Path, today: date | None = None) -> ApprovedSet:
    expected = ApprovedSet.model_validate(json.loads(lock_file.read_text(encoding="utf-8")))
    actual = lock(workspace, expected.sha, today).lock
    differences = {
        asset_id: {"lock": expected.lock.get(asset_id), "actual": actual.get(asset_id)}
        for asset_id in sorted(set(expected.lock) | set(actual))
        if expected.lock.get(asset_id) != actual.get(asset_id)
    }
    if differences:
        raise LockMismatch(differences)
    return expected
