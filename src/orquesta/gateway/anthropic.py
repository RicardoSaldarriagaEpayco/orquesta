import os
from collections.abc import Mapping
from typing import Any

from orquesta.errors import ProviderError
from orquesta.gateway.provider import ModelRequest, ModelResponse, Usage

PER_MILLION = 1_000_000


class AnthropicProvider:
    def __init__(self, prices: Mapping[str, tuple[float, float]], client: Any = None) -> None:
        self.prices = dict(prices)
        self._client = client

    def name(self) -> str:
        return "anthropic"

    def _connect(self) -> Any:
        if self._client is None:
            key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not key:
                raise ProviderError("anthropic", "falta ANTHROPIC_API_KEY en el entorno del gateway")
            import anthropic

            self._client = anthropic.Anthropic(api_key=key)
        return self._client

    def complete(self, request: ModelRequest) -> ModelResponse:
        if request.model not in self.prices:
            raise ProviderError("anthropic", f"sin precio registrado para {request.model}")
        client = self._connect()
        try:
            message = client.messages.create(
                model=request.model,
                system=request.system,
                messages=[m.model_dump() for m in request.messages],
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            )
        except Exception as error:
            raise ProviderError("anthropic", f"la llamada falló ({type(error).__name__})") from None
        text = "".join(getattr(block, "text", "") for block in message.content if block.type == "text")
        usage = Usage(input_tokens=message.usage.input_tokens, output_tokens=message.usage.output_tokens)
        input_price, output_price = self.prices[request.model]
        cost = (usage.input_tokens * input_price + usage.output_tokens * output_price) / PER_MILLION
        return ModelResponse(text=text, stop_reason=message.stop_reason or "", usage=usage, cost_usd=round(cost, 6))
