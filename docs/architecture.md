# Arquitectura

Principio rector: **el workspace del tenant es el plano de conocimiento y reglas; `orquesta` es el plano de control y
ejecución.** El núcleo lee activos y reglas del workspace por git, fijados a un SHA aprobado; no los copia ni lee el
árbol de trabajo.

```
UI web (bandeja de aprobaciones, diffs, trazas)                       ← F4
        │  OIDC
API HTTP ── AuthZ/RBAC ── Auditoría (eventos encadenados con HMAC) ── OpenTelemetry   ← F2
   │
LangGraph (grafos de triage, análisis de repo, revisión de PR, fix con aprobación)    ← F2/F3
   │  checkpointer Postgres · nodos interrupt = aprobación humana
   ├─ Registry       ← git show <sha>:.claude/... + catalog.yaml → AgentAssetManifest     ✅ F1
   ├─ Policy core    ← policy.yaml + workspace.yaml del SHA; hooks y CI como adaptadores  ✅ F1
   ├─ Model gateway  ← allowlist del tenant, costo, credencial de corta vida (F2)         ✅ F1 parcial
   ├─ Evals          ← suites del tenant, métricas, PromotionRecord                       ✅ F1
   ├─ Evidence       ← EvidenceReceipt firmado por SHA                                    ⏳ F1
   ├─ Tool layer MCP ← host git (GitHub App), tracker de tickets, herramientas internas   ← F2/F3
   ├─ Sandbox runner ← contenedor efímero rootless por episodio, egress por allowlist     ← F2
   ├─ QA runner      ← proceso aparte que guarda secretos; el agente dispara jobs con nombre ← F3
   └─ Knowledge      ← pgvector sobre rutas autorizadas por clasificación                 ← F4
```

## Módulos actuales (`src/orquesta/`)

| Módulo | Qué hace |
|---|---|
| `workspace.py` | Lee archivos del workspace con `git show` solo desde commits alcanzables de la rama aprobada |
| `registry/` | `AgentAssetManifest`, resolución por `git ls-tree`, digest por activo, `ApprovedSet` y lock |
| `policy/` | Parser de shell, reglas, `Environment` (hechos del entorno separados de la decisión), carga de reglas, fixtures |
| `gateway/` | `ModelProvider`, `FakeProvider`, `AnthropicProvider`, allowlist y evento `ModelCall` |
| `audit/` | Esquema Postgres con roles, cadena HMAC, redactor, llave `0600`, escritura opcional por `ORQUESTA_AUDIT_DSN` |
| `evals/` | Suites, corrida por mayoría, métricas, `PromotionRecord` |
| `cli.py` | `registry`, `policy`, `audit`, `eval` ([contracts/cli.md](../contracts/cli.md)) |

## Decisiones

- **Versiones inmutables sin copia**: un cambio de activo entra por PR al workspace, pasa evaluaciones y recién
  entonces se mueve el puntero aprobado.
- **Hechos separados de la decisión**: el motor de políticas no consulta `git`; pregunta a un `Environment`. Los
  fixtures de paridad declaran los hechos y no necesitan repos reales.
- **Auditoría resistente**: el rol que escribe no tiene `UPDATE`, `DELETE` ni `TRUNCATE`; `mac = HMAC-SHA256(llave,
  prev_mac || evento canónico)`; la llave vive fuera de la base (archivo `0600` en F1, vault o KMS en F2).
- **Redis diferido**: Postgres cubre cola (`SKIP LOCKED`) y checkpointer.
- **Sin worktrees en el host** para episodios: clones dentro del sandbox.
- **Ruta caliente liviana**: `policy eval` no carga `pydantic` ni la auditoría si no hace falta (~165 ms con el
  adaptador).
