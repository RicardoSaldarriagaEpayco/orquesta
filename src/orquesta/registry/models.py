from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

HEX40 = r"^[0-9a-f]{40}$"
NAME = r"^[a-z0-9][a-z0-9-]*$"

AssetType = Literal["agent", "skill", "hook", "mcp", "engine", "image"]
Classification = Literal["public", "internal", "confidential", "regulated"]
Effect = Literal["commit", "push", "pr", "jira-comment", "jira-transition", "third-party"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExternalSource(Strict):
    url: str = Field(pattern=r"^https?://\S+$")
    commit: str = Field(pattern=HEX40)


class Approval(Strict):
    by: str
    at: datetime
    sha: str = Field(pattern=HEX40)


class AgentAssetManifest(Strict):
    id: str = Field(pattern=r"^(agent|skill|hook|mcp|engine|image)/[a-z0-9][a-z0-9-]*$")
    type: AssetType
    name: str = Field(pattern=NAME)
    description: str | None = Field(default=None, min_length=1)
    tools: list[str] | None = None
    disable_model_invocation: bool | None = None
    version: str = Field(pattern=r"^[0-9a-f]{7,12}$")
    sha: str = Field(pattern=HEX40)
    path: str = Field(pattern=r"^\.claude/(agents|skills)/[A-Za-z0-9._/-]+$")
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    owner: str = Field(min_length=1)
    source: Literal["workspace"] | ExternalSource
    license: str | None = None
    classification: Classification
    egress: list[str]
    external_effects: list[Effect]
    evals: list[str]
    expires: date | None = None
    approvals: list[Approval]

    @field_validator("path")
    @classmethod
    def _inside_claude(cls, value: str) -> str:
        if ".." in value:
            raise ValueError("la ruta no puede contener ..")
        return value

    @field_validator("egress", "external_effects", "evals")
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("hay elementos repetidos")
        return value

    @model_validator(mode="after")
    def _governance(self) -> Self:
        if self.id != f"{self.type}/{self.name}":
            raise ValueError(f"id {self.id} no coincide con {self.type}/{self.name}")
        if isinstance(self.source, ExternalSource) and not self.license:
            raise ValueError("license es obligatoria si source no es workspace")
        if self.external_effects and self.disable_model_invocation is not True:
            raise ValueError("external_effects exige disable-model-invocation: true")
        return self

    def to_json(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude_none=True)
