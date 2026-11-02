# Implementation Plan: orquestación de solo lectura (F2)

**Branch**: `002-solo-lectura` | **Date**: 2026-11-01 | **Spec**: [spec.md](spec.md)

## Summary

Encadenar los motores de F1 en grafos de LangGraph con estado en Postgres y aprobaciones por `interrupt`, servirlos
por una API HTTP con roles por repo, y correr el trabajo de los agentes en contenedores rootless que solo salen por un
proxy con allowlist y usan credenciales de corta vida contra el gateway.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies** (versión exacta, verificadas el 2026-11-01): `langgraph==1.2.19`,
`langgraph-checkpoint-postgres==3.2.0`, `fastapi==0.162.0`, `uvicorn==0.54.0`, `opentelemetry-sdk==1.45.2`,
`mcp==2.3.0`. Se agregan en la tarea que las usa, no antes.

**Storage**: Postgres 16 de la auditoría; esquema `graph` con rol `graph_writer` para el checkpointer.

**Testing**: pytest con Postgres real (Docker), `FakeProvider`, fuente de tickets de archivo, contenedor real solo en
las pruebas del sandbox (se saltan si no hay motor de contenedores rootless).

**Target Platform**: Linux con Docker rootless o Podman.

**Constraints**: la ruta caliente de `policy eval` no importa LangGraph, FastAPI ni OpenTelemetry (sigue bajo 300 ms).

## API de LangGraph verificada

```python
from langgraph.types import interrupt, Command
from langgraph.checkpoint.postgres import PostgresSaver

def approve(state):
    answer = interrupt({"proposal": state["proposal"]})
    return {"decision": answer["decision"]}

with PostgresSaver.from_conn_string(dsn) as saver:
    saver.setup()
    app = graph.compile(checkpointer=saver)
    app.invoke({"ticket_id": "T-1"}, {"configurable": {"thread_id": run_id}})
    app.get_state(config).interrupts
    app.invoke(Command(resume={"decision": "approve", "actor": "ana"}), config)
```

`setup()` crea `checkpoints`, `checkpoint_blobs`, `checkpoint_writes` y `checkpoint_migrations` en el `search_path`
de la conexión; el DSN de `graph_writer` fija `search_path=graph`.

## Constitution Check

| Principio | Cómo se cumple |
|---|---|
| I. Datos del tenant | Tickets, allowlist de red y tokens viven del lado del tenant u operador; el estado del grafo guarda referencias, no texto del ticket |
| II. Políticas fuera del modelo | El nodo `policy` llama al motor de F1; el proxy de salida es código determinista |
| III. Humano en el lazo | Toda propuesta pasa por un `interrupt`; F2 no tiene efectos externos (FR-054) |
| IV. Evidencia | `graph.step`, `approval`, `authz`, `egress` encadenados en la auditoría |
| V. Secretos | Llaves solo en el gateway; el episodio recibe credencial de corta vida; trazas por el redactor |
| VI. Motor y proveedor | El grafo usa `ModelProvider`; el sandbox es una interfaz con runner de Docker o Podman |
| VII. Pequeño y reversible | Una dependencia por tarea; cada tarea es un PR bajo 800 líneas |

## Project Structure

```text
src/orquesta/
├── graphs/
│   ├── checkpoint.py      # conexión del checkpointer con el rol y esquema propios
│   ├── tickets.py         # TicketSource, FileTicketSource, McpTicketSource
│   ├── triage.py          # estado, nodos y grafo de triage
│   ├── repo_analysis.py   # informe de repo en sandbox
│   └── pr_review.py       # comentario sugerido
├── api/
│   ├── app.py             # FastAPI, rutas /v1
│   └── auth.py            # tokens con hash, roles por repo
├── sandbox/
│   ├── runner.py          # SandboxRunner, DockerRunner rootless
│   └── egress.py          # proxy CONNECT con allowlist
├── gateway/credential.py  # credencial de episodio firmada y con vencimiento
└── telemetry.py           # spans con redactor, exportación opcional
docker/initdb/20-graph.sh  # esquema graph y rol graph_writer
contracts/
├── ticket.schema.json
├── triage-result.schema.json
└── api.md
```

## Decisiones

- **Mismo servidor, esquema aparte**: evita un segundo Postgres; el rol del checkpointer no tiene permisos en la
  auditoría y el de auditoría no los tiene en `graph`.
- **Aprobación como respuesta, no como estado editado**: se reanuda con `Command(resume=…)` y el actor sale del token
  de la API o de la identidad del CLI, nunca del cuerpo.
- **Proxy propio y mínimo**: un proxy `CONNECT` en asyncio con allowlist de hosts exactos; el contenedor corre en una
  red interna sin ruta por defecto y solo ve al proxy.
- **Credencial de episodio**: HMAC con una llave del gateway (`0600`), claims `run_id`, `exp`, `models`,
  `budget_usd`. Un JWT completo no aporta nada en un solo proceso.
- **Importes perezosos**: los módulos de F2 se importan solo en los subcomandos que los usan.
