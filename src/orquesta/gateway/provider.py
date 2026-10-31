from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from orquesta.errors import ProviderError


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str


class ModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1)
    system: str = ""
    messages: list[Message] = Field(min_length=1)
    max_tokens: int = Field(gt=0)
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    metadata: dict[str, str] = Field(default_factory=dict)


class Usage(BaseModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class ModelResponse(BaseModel):
    text: str
    stop_reason: str
    usage: Usage
    cost_usd: float = Field(ge=0.0)


class ModelProvider(Protocol):
    def name(self) -> str: ...

    def complete(self, request: ModelRequest) -> ModelResponse: ...


class FakeProvider:
    def __init__(self, answers: dict[str, str]) -> None:
        self.answers = dict(answers)
        self.calls: list[ModelRequest] = []

    def name(self) -> str:
        return "fake"

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        case_id = request.metadata.get("case_id", "")
        if case_id not in self.answers:
            raise ProviderError("fake", f"sin respuesta para el caso {case_id or '(sin case_id)'}")
        text = self.answers[case_id]
        prompt = " ".join([request.system, *(m.content for m in request.messages)])
        usage = Usage(input_tokens=len(prompt.split()), output_tokens=len(text.split()))
        return ModelResponse(text=text, stop_reason="end_turn", usage=usage, cost_usd=0.0)
