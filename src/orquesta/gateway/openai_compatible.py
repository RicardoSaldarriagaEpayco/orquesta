import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping

from orquesta.errors import ProviderError
from orquesta.gateway.provider import ModelRequest, ModelResponse, Usage

PER_MILLION = 1_000_000
Post = Callable[[str, dict[str, str], bytes, float], dict[str, object]]


def _post(url: str, headers: dict[str, str], body: bytes, timeout: float) -> dict[str, object]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


class OpenAICompatibleProvider:
    def __init__(
        self,
        name: str,
        base_url: str,
        prices: Mapping[str, tuple[float, float]],
        key_env: str = "",
        timeout_s: float = 60.0,
        post: Post = _post,
    ) -> None:
        if not base_url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
            raise ProviderError(name, "base_url debe ser https o un servidor local")
        self._name, self.base_url, self.prices = name, base_url.rstrip("/"), dict(prices)
        self.key_env, self.timeout_s, self._post = key_env, timeout_s, post

    def name(self) -> str:
        return self._name

    def complete(self, request: ModelRequest) -> ModelResponse:
        if request.model not in self.prices:
            raise ProviderError(self._name, f"sin precio registrado para {request.model}")
        headers = {"Content-Type": "application/json"}
        if self.key_env:
            key = os.environ.get(self.key_env, "")
            if not key:
                raise ProviderError(self._name, f"falta {self.key_env} en el entorno del gateway")
            headers["Authorization"] = f"Bearer {key}"
        messages = [{"role": "system", "content": request.system}] if request.system else []
        messages += [m.model_dump() for m in request.messages]
        body = json.dumps(
            {
                "model": request.model,
                "messages": messages,
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
            }
        ).encode()
        try:
            data = self._post(f"{self.base_url}/chat/completions", headers, body, self.timeout_s)
            choice = data["choices"][0]
            usage = Usage(input_tokens=data["usage"]["prompt_tokens"], output_tokens=data["usage"]["completion_tokens"])
            text = choice["message"]["content"] or ""
            stop = choice.get("finish_reason") or ""
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise ProviderError(self._name, f"la llamada falló ({type(error).__name__})") from None
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ProviderError(self._name, f"respuesta inesperada ({type(error).__name__})") from None
        input_price, output_price = self.prices[request.model]
        cost = (usage.input_tokens * input_price + usage.output_tokens * output_price) / PER_MILLION
        return ModelResponse(text=text, stop_reason=stop, usage=usage, cost_usd=round(cost, 6))
