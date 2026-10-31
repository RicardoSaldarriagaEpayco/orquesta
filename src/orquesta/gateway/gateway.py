import time
from collections.abc import Callable, Sequence
from fnmatch import fnmatchcase
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from orquesta.errors import ModelNotAllowed, ProviderNotAllowed
from orquesta.gateway.provider import ModelProvider, ModelRequest, ModelResponse


class ModelCall(BaseModel):
    kind: Literal["model_call"] = "model_call"
    actor: str
    tenant: str = Field(pattern=r"^[a-z0-9-]+$")
    provider: str
    model: str
    tools: list[str] = Field(default_factory=list)
    decision: str = Field(max_length=512)
    latency_ms: int = Field(ge=0)
    cost_usd: float | None = Field(default=None, ge=0.0)
    refs: dict[str, str] = Field(default_factory=dict)


class AuditSink(Protocol):
    def write(self, event: ModelCall) -> None: ...


class Allowlist:
    def __init__(self, patterns: Sequence[str]) -> None:
        self.patterns = tuple(patterns)

    def allows_provider(self, provider: str) -> bool:
        return any(p.split("/", 1)[0] == provider for p in self.patterns)

    def allows(self, provider: str, model: str) -> bool:
        return any(fnmatchcase(f"{provider}/{model}", p) for p in self.patterns)


class Gateway:
    def __init__(
        self,
        allowlist: Allowlist,
        sink: AuditSink,
        actor: str,
        tenant: str,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.allowlist, self.sink, self.actor, self.tenant, self.clock = allowlist, sink, actor, tenant, clock

    def complete(self, provider: ModelProvider, request: ModelRequest) -> ModelResponse:
        name = provider.name()
        if not self.allowlist.allows_provider(name):
            raise ProviderNotAllowed(name)
        if not self.allowlist.allows(name, request.model):
            raise ModelNotAllowed(name, request.model)
        refs = {"case_id": request.metadata["case_id"]} if "case_id" in request.metadata else {}
        started = self.clock()
        try:
            response = provider.complete(request)
        except Exception as error:
            self._record(name, request.model, started, None, refs, f"error: {type(error).__name__}")
            raise
        self._record(name, request.model, started, response.cost_usd, refs, f"ok: {response.stop_reason}")
        return response

    def _record(
        self, provider: str, model: str, started: float, cost: float | None, refs: dict[str, str], decision: str
    ) -> None:
        latency = max(0, round((self.clock() - started) * 1000))
        self.sink.write(
            ModelCall(
                actor=self.actor,
                tenant=self.tenant,
                provider=provider,
                model=model,
                decision=decision,
                latency_ms=latency,
                cost_usd=cost,
                refs=refs,
            )
        )
