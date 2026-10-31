# orquesta

Núcleo open source para gobernar agentes de IA de ingeniería: qué agentes y skills están aprobados, qué puede hacer
cada uno, qué quedó registrado y cómo se mide si un cambio los mejora o los empeora.

Complementa a Claude Code; no lo reemplaza. Los agentes, skills y reglas de cada equipo o empresa (*tenant*) viven en
su propio repo (*workspace*). `orquesta` solo trae los motores genéricos y lee el workspace por SHA aprobado, nunca del
árbol de trabajo.

## Qué hace

| Módulo | Para qué |
|---|---|
| `registry` | Resuelve los agentes y skills de un SHA aprobado, con su catálogo y un digest por activo, y los fija en un lock |
| `policy` | Decide `allow`, `deny` o `ask` para cada acción de un agente con las reglas del tenant, y niega lo que no reconoce |
| `audit` | Guarda cada decisión en una cadena HMAC de solo anexado en Postgres y verifica que nadie la alteró |
| `gateway` | Llama solo a los modelos permitidos por el tenant y registra proveedor, modelo, latencia y costo, sin el texto |
| `evals` | Corre suites de casos y compara contra la línea base antes de promover un cambio |

## Uso

```bash
uv sync
export ORQUESTA_ACTOR=tu-usuario
uv run orquesta registry list --workspace ../mi-workspace --sha origin/main --json
echo '{"tool_name": "Write", "tool_input": {"file_path": "/repo/a"}, "cwd": "/repo"}' |
  uv run orquesta policy eval --workspace ../mi-workspace --sha origin/main --hook
```

`examples/workspace/` es un workspace de ejemplo genérico y `examples/demo.sh` recorre registro, política y evaluación
de punta a punta sobre una copia temporal.

Lo que el workspace del tenant necesita y el formato de cada archivo está en [`contracts/`](contracts/). Los comandos,
códigos de salida y variables de entorno, en [`contracts/cli.md`](contracts/cli.md).

Para la auditoría: `AUDIT_OWNER_PASSWORD=… AUDIT_WRITER_PASSWORD=… docker compose up -d`, una llave en
`~/.config/orquesta/audit.key` con permisos `0600` y `ORQUESTA_AUDIT_DSN` con la credencial de `audit_writer`.

## Documentación

- [Arquitectura](docs/architecture.md) y [roadmap](docs/roadmap.md)
- [Spec](specs/001-nucleo/spec.md) y [tareas](specs/001-nucleo/tasks.md)
- [Adaptador de Claude Code](adapters/claude-code/README.md)
- [Constitución](.specify/memory/constitution.md) y [ADRs](docs/adr/)

## Reglas del repo

- Sin datos de ningún tenant: ni nombres de repos, ni llaves, ni reglas, ni contexto. Los datos de prueba son genéricos
  y `scripts/tenant_leak.py` lo verifica en CI.
- Una instalación por tenant (single-tenant), aislada en datos, llaves, red y auditoría.
- Sin identidad configurada, `orquesta` no arranca.

## Estado

F1 (núcleo headless) en cierre. Todavía sin versión publicada.

## Licencia

[Apache-2.0](LICENSE).
