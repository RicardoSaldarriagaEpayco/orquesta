# Contrato: decisión de política

Un solo motor (`orquesta policy eval`) decide. Los hooks del cliente de agentes, el CI y la plataforma son adaptadores:
traducen su entrada a `PolicyRequest` y su salida desde `PolicyDecision`, sin lógica de decisión propia.

## Entrada: `PolicyRequest` (JSON por stdin)

```json
{
  "entrypoint": "claude-wsl | claude-desktop | ci | platform",
  "tool": "Bash | PowerShell | Write | Edit | NotebookEdit | Skill | EnterWorktree | Agent",
  "input": { "...": "tool_input tal como lo entrega el cliente" },
  "cwd": "/ruta/absoluta",
  "actor": "identidad del operador"
}
```

- Las rutas UNC de WSL (`\\wsl.localhost\<distro>\...`) se normalizan a rutas Linux antes de evaluar.
- Las reglas se leen de `policy.yaml` y `workspace.yaml` del SHA aprobado del workspace del tenant, no del árbol de
  trabajo. Si `--workspace` es un worktree enlazado, la raíz es el checkout principal.
- Con `--hook`, la entrada es el JSON `PreToolUse` del cliente (`tool_name`, `tool_input`, `cwd`) y el actor sale de la
  identidad del operador.

## Salida: `PolicyDecision` (JSON por stdout)

```json
{ "verdict": "allow | deny | ask", "rule_id": "readonly-repo", "reason": "texto para la persona", "policy_sha": "<40 hex>" }
```

Con `--hook`: `allow` no imprime nada; `deny` y `ask` imprimen
`{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "<verdict>", "permissionDecisionReason": "<reason> [<rule_id>]"}}`.

| Código de salida | Significado |
|---|---|
| `0` | Decisión emitida (cualquier `verdict`) |
| `2` | Entrada ilegible; el adaptador la trata como `deny` |
| `3` | Reglas del tenant ilegibles o SHA no aprobado; el adaptador la trata como `deny` |

Un adaptador que no encuentra el motor, recibe `2` o `3`, o lee una respuesta ilegible, niega (falla cerrado).

## Reglas (`rule_id`)

| `rule_id` | Niega | Datos del tenant |
|---|---|---|
| `self-merge` | `gh pr merge` y el merge por la API | — |
| `push-protected` | `git push` a una rama protegida o solo local | `protected_branches`, `local_branches` |
| `ai-attribution` | crear o editar un PR cuyo cuerpo o `--body-file` trae atribución de IA | `ai_attribution_patterns` |
| `pr-without-receipt` | crear un PR de un commit sin recibo de la puerta de calidad | `pr_requires_receipt` |
| `worktree-outside-root` | worktrees dentro de un repo de producto | `worktree_root` |
| `spec-outside-root` | spec-kit y `specs/`/`.specify/` dentro de un repo de producto | `spec_root` |
| `readonly-repo` | escrituras y comandos con efecto en un repo de solo lectura | `repos[].write: false` de `workspace.yaml` |
| `unknown-input` | una herramienta que el motor no evalúa o una entrada incompleta | — |

## Paridad (SC-008)

Los casos de cada adaptador se escriben como fixture `PolicyRequest → {verdict, rule_id}` con los hechos del entorno
declarados (repos, ramas, recibos). `orquesta policy test --fixtures <archivo>` los corre con las reglas de un SHA; el
fixture genérico vive en `tests/policy/fixtures.yaml` y cada tenant guarda el suyo en su workspace. Un mismo caso con
dos veredictos distintos entre adaptadores falla.
