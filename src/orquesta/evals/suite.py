from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from orquesta.errors import SuiteInvalid
from orquesta.workspace import Workspace

ID = r"^[a-z0-9-]+$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExpectAgent(Strict):
    agent: str = Field(pattern=r"^[a-z0-9-]+-agent$")


class ExpectAsk(Strict):
    ask: Literal[True]


class ExpectNoAction(Strict):
    no_action: Literal[True]


Expected = ExpectAgent | ExpectAsk | ExpectNoAction


def outcome(expected: Expected) -> str:
    if isinstance(expected, ExpectAgent):
        return f"agent:{expected.agent}"
    return "ask" if isinstance(expected, ExpectAsk) else "no_action"


class EpisodeChecks(Strict):
    tools_allowed: list[str] | None = None
    tools_required: list[str] = Field(default_factory=list)
    final_pattern: str | None = Field(default=None, min_length=1)
    receipts: list[str] = Field(default_factory=list)


class EvalCase(Strict):
    id: str = Field(pattern=ID)
    ticket: str = Field(pattern=r"^[A-Z][A-Z0-9]+-[0-9]+$")
    project: str
    labels: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=10, max_length=400)
    expected: Expected
    near_miss: bool
    tags: list[str] = Field(default_factory=list)
    checks: EpisodeChecks | None = None


class EvalSuite(Strict):
    suite: str = Field(pattern=ID)
    runs: int = Field(ge=1)
    engine: str
    timeout_s: int = Field(ge=1)
    allowed_tools: list[str]
    margin: float = Field(default=0.0, ge=0.0, le=1.0)
    cases: list[EvalCase] = Field(min_length=30)

    @model_validator(mode="after")
    def _unique_ids(self) -> "EvalSuite":
        ids = [case.id for case in self.cases]
        if len(set(ids)) != len(ids):
            raise ValueError("hay ids de caso repetidos")
        return self


def parse(name: str, text: str) -> EvalSuite:
    try:
        return EvalSuite.model_validate(yaml.safe_load(text))
    except yaml.YAMLError as error:
        raise SuiteInvalid(name, f"YAML inválido: {error.problem}") from error
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(part) for part in first["loc"]) or "suite"
        raise SuiteInvalid(name, f"{where}: {first['msg']}") from error


def load(workspace: Workspace, sha: str, path: str) -> EvalSuite:
    try:
        return parse(path, workspace.read(sha, path))
    except FileNotFoundError as error:
        raise SuiteInvalid(path, "no existe en el SHA") from error
