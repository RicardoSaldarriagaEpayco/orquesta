import json
import logging

import pytest

from orquesta.errors import ModelNotAllowed, ProviderError, ProviderNotAllowed
from orquesta.gateway.gateway import Allowlist, Gateway, ModelCall
from orquesta.gateway.provider import FakeProvider, ModelRequest

SECRET_PROMPT = "texto confidencial del ticket"
CANARY_KEY = "sk-canario-0123456789"


class MemorySink:
    def __init__(self) -> None:
        self.events: list[ModelCall] = []

    def write(self, event: ModelCall) -> None:
        self.events.append(event)


class ExplodingProvider:
    def __init__(self, provider: str = "anthropic") -> None:
        self.provider = provider
        self.key = CANARY_KEY

    def name(self) -> str:
        return self.provider

    def complete(self, request: ModelRequest):
        raise AssertionError("no debía llamarse")


def request(model: str = "routing-v1", case_id: str = "case-1") -> ModelRequest:
    return ModelRequest(
        model=model,
        system="Elige un agente.",
        messages=[{"role": "user", "content": SECRET_PROMPT}],
        max_tokens=64,
        metadata={"case_id": case_id},
    )


@pytest.fixture
def sink() -> MemorySink:
    return MemorySink()


def gateway(sink: MemorySink, *patterns: str) -> Gateway:
    ticks = iter([10.0, 10.25])
    allow = patterns or ("anthropic/claude-sonnet-5-5", "fake/*")
    return Gateway(Allowlist(allow), sink, actor="someone", tenant="acme", clock=lambda: next(ticks))


def test_fake_provider_answers_by_case_id() -> None:
    provider = FakeProvider({"case-1": "agent: reviewer"})
    response = provider.complete(request())
    assert response.text == "agent: reviewer"
    assert response.cost_usd == 0.0
    assert provider.complete(request()) == response


def test_fake_provider_without_answer_is_a_provider_error() -> None:
    with pytest.raises(ProviderError):
        FakeProvider({}).complete(request(case_id="desconocido"))


def test_model_outside_the_allowlist_is_rejected_without_calling(sink) -> None:
    with pytest.raises(ModelNotAllowed):
        gateway(sink).complete(ExplodingProvider(), request(model="claude-opus-5-5"))
    assert sink.events == []


def test_provider_outside_the_allowlist_is_rejected_without_calling(sink) -> None:
    with pytest.raises(ProviderNotAllowed):
        gateway(sink).complete(ExplodingProvider("otro"), request())
    assert sink.events == []


def test_each_call_writes_a_model_call_without_text(sink) -> None:
    gateway(sink).complete(FakeProvider({"case-1": "agent: reviewer"}), request())
    [event] = sink.events
    assert (event.kind, event.provider, event.model) == ("model_call", "fake", "routing-v1")
    assert event.latency_ms == 250
    assert event.cost_usd == 0.0
    assert event.refs == {"case_id": "case-1"}
    dumped = event.model_dump_json()
    assert SECRET_PROMPT not in dumped and "agent: reviewer" not in dumped


def test_a_failed_call_is_recorded_and_raised(sink) -> None:
    with pytest.raises(ProviderError):
        gateway(sink).complete(FakeProvider({}), request())
    [event] = sink.events
    assert event.decision == "error: ProviderError"
    assert event.cost_usd is None


def test_provider_key_never_reaches_events_or_logs(sink, caplog) -> None:
    caplog.set_level(logging.DEBUG)

    class KeyedFake(FakeProvider):
        key = CANARY_KEY

    gateway(sink).complete(KeyedFake({"case-1": "agent: reviewer"}), request())
    with pytest.raises(ModelNotAllowed):
        gateway(sink).complete(ExplodingProvider(), request(model="otro"))
    everything = json.dumps([e.model_dump() for e in sink.events]) + caplog.text
    assert CANARY_KEY not in everything
