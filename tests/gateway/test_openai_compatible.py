import json
import urllib.error

import pytest

from orquesta.errors import ProviderError
from orquesta.gateway.openai_compatible import OpenAICompatibleProvider
from orquesta.gateway.provider import ModelRequest

KEY = "sk-local-canario-0123456789"
PRICES = {"llama-4-70b": (0.5, 1.5)}


class Recorder:
    def __init__(self, answer=None, error: Exception | None = None) -> None:
        self.answer, self.error, self.calls = answer, error, []

    def __call__(self, url, headers, body, timeout):
        self.calls.append((url, headers, json.loads(body), timeout))
        if self.error:
            raise self.error
        return self.answer


ANSWER = {
    "choices": [{"message": {"content": "agent: reviewer-agent"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 2000, "completion_tokens": 20},
}


def request(model: str = "llama-4-70b") -> ModelRequest:
    return ModelRequest(model=model, system="s", messages=[{"role": "user", "content": "hola"}], max_tokens=16)


def provider(post, key_env: str = "") -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider("vllm", "http://127.0.0.1:8000/v1", PRICES, key_env=key_env, post=post)


def test_maps_chat_completions_and_cost() -> None:
    post = Recorder(ANSWER)
    response = provider(post).complete(request())
    assert response.text == "agent: reviewer-agent" and response.stop_reason == "stop"
    assert response.cost_usd == pytest.approx((2000 * 0.5 + 20 * 1.5) / 1_000_000)
    url, headers, body, _ = post.calls[0]
    assert url == "http://127.0.0.1:8000/v1/chat/completions" and "Authorization" not in headers
    assert body["messages"][0] == {"role": "system", "content": "s"}


def test_sends_the_key_only_as_bearer(monkeypatch) -> None:
    monkeypatch.setenv("LOCAL_LLM_KEY", KEY)
    post = Recorder(ANSWER)
    provider(post, "LOCAL_LLM_KEY").complete(request())
    assert post.calls[0][1]["Authorization"] == f"Bearer {KEY}"


def test_missing_key_or_price_fails_before_calling(monkeypatch) -> None:
    monkeypatch.delenv("LOCAL_LLM_KEY", raising=False)
    post = Recorder(ANSWER)
    with pytest.raises(ProviderError, match="LOCAL_LLM_KEY"):
        provider(post, "LOCAL_LLM_KEY").complete(request())
    with pytest.raises(ProviderError, match="sin precio"):
        provider(post).complete(request("otro"))
    assert post.calls == []


@pytest.mark.parametrize(
    ("answer", "error"),
    [(None, urllib.error.URLError(f"refused {KEY}")), ({"choices": []}, None), ({"nada": 1}, None)],
)
def test_failures_are_provider_errors_without_the_key(monkeypatch, answer, error) -> None:
    monkeypatch.setenv("LOCAL_LLM_KEY", KEY)
    with pytest.raises(ProviderError) as raised:
        provider(Recorder(answer, error), "LOCAL_LLM_KEY").complete(request())
    assert KEY not in str(raised.value) and raised.value.__cause__ is None


def test_plain_http_to_a_remote_host_is_rejected() -> None:
    with pytest.raises(ProviderError, match="https"):
        OpenAICompatibleProvider("x", "http://example.com/v1", PRICES)
