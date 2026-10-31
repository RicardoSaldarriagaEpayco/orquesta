from types import SimpleNamespace

import pytest

from orquesta.errors import ProviderError
from orquesta.gateway.anthropic import AnthropicProvider
from orquesta.gateway.provider import ModelRequest

KEY = "sk-ant-canario-0123456789abcdef"
PRICES = {"claude-sonnet-5-5": (3.0, 15.0)}


class FakeMessages:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="agent: reviewer-agent")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=1000, output_tokens=10),
        )


def request(model: str = "claude-sonnet-5-5") -> ModelRequest:
    return ModelRequest(model=model, system="s", messages=[{"role": "user", "content": "hola"}], max_tokens=16)


def test_maps_request_response_and_cost() -> None:
    messages = FakeMessages()
    response = AnthropicProvider(PRICES, SimpleNamespace(messages=messages)).complete(request())
    assert response.text == "agent: reviewer-agent" and response.stop_reason == "end_turn"
    assert response.cost_usd == pytest.approx((1000 * 3.0 + 10 * 15.0) / 1_000_000)
    [call] = messages.calls
    assert call["model"] == "claude-sonnet-5-5" and call["messages"] == [{"role": "user", "content": "hola"}]


def test_model_without_price_fails_before_calling() -> None:
    messages = FakeMessages()
    with pytest.raises(ProviderError, match="sin precio"):
        AnthropicProvider(PRICES, SimpleNamespace(messages=messages)).complete(request("claude-haiku-5-5"))
    assert messages.calls == []


def test_missing_key_fails_without_network(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="ANTHROPIC_API_KEY"):
        AnthropicProvider(PRICES).complete(request())


def test_sdk_errors_do_not_leak_the_key(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    failing = FakeMessages(RuntimeError(f"401 con la llave {KEY}"))
    with pytest.raises(ProviderError) as error:
        AnthropicProvider(PRICES, SimpleNamespace(messages=failing)).complete(request())
    assert KEY not in str(error.value) and error.value.__cause__ is None
