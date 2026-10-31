# Adaptador de Claude Code

`policy-hook.sh` es un hook `PreToolUse` que delega la decisión en `orquesta policy eval --hook` con las reglas del
SHA aprobado del workspace. Si el motor falta, sale con código distinto de `0` o responde algo ilegible, niega.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|PowerShell|Write|Edit|NotebookEdit|Skill|EnterWorktree|Agent",
        "hooks": [{ "type": "command", "command": "ORQUESTA_WORKSPACE=/ruta/al/workspace /ruta/a/policy-hook.sh" }]
      }
    ]
  }
}
```

| Variable | Uso |
|---|---|
| `ORQUESTA_WORKSPACE` | Ruta del workspace del tenant (obligatoria) |
| `ORQUESTA_APPROVED_REF` | Ref aprobada (por defecto `origin/main`) |
| `ORQUESTA_BIN` | Ejecutable de `orquesta` si no está en el `PATH` |
| `ORQUESTA_ACTOR` | Identidad del operador |

Conviene que cada hook conserve un prefiltro de texto barato antes de llamar al motor, para que las acciones comunes no
paguen el arranque de Python.
