# Contrato: `ModelProvider` y gateway de modelos (F1)

Cubre FR-037 a FR-039 en su forma de F1 (R11). Interfaz interna del núcleo; los episodios aislados y la credencial
de corta vida llegan en F2.

## Interfaz

| Operación | Entrada | Salida | Errores |
|---|---|---|---|
| `complete` | `ModelRequest`: `model`, `system`, `messages`, `max_tokens`, `temperature`, `metadata.case_id` | `ModelResponse`: `text`, `stop_reason`, `usage.input_tokens`, `usage.output_tokens`, `cost_usd` | `ModelNotAllowed`, `ProviderNotAllowed`, `ProviderError` |
| `name` | — | id del proveedor (`fake`, `anthropic`) | — |

## Reglas del gateway

1. Antes de llamar, el gateway compara `provider/model` con la allowlist del tenant; fuera de ella → `ModelNotAllowed`
   sin llamada de red (FR-038).
2. La llave del proveedor la lee solo el gateway; nunca se pasa a un activo, a un log ni a `refs` de auditoría.
3. Cada llamada escribe un `AuditEvent` `kind: model_call` con `provider`, `model`, `latency_ms`, `cost_usd` y
   `refs.case_id`; el texto del prompt y de la respuesta no se guarda (FR-030).
4. Antes de escribir el evento, los campos pasan por el redactor de secretos; un canario conocido nunca aparece en
   la tabla ni en logs (SC-007).
5. `FakeProvider` es determinista: responde por tabla `case_id → texto` y sirve para CI y para las evaluaciones con
   proveedor falso (US7).

## Configuración (del tenant, fuera del núcleo)

```yaml
models:
  default: anthropic/claude-sonnet-5-5
  allow:
    - anthropic/claude-sonnet-5-5
    - anthropic/claude-haiku-5-5
    - fake/*
```
