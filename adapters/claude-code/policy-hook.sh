#!/usr/bin/env bash
set -uo pipefail

emit() {
  python3 -c 'import json, sys; print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": sys.argv[1], "permissionDecisionReason": sys.argv[2]}}))' "$1" "$2"
}

engine="${ORQUESTA_BIN:-orquesta}"
workspace="${ORQUESTA_WORKSPACE:-}"
payload="$(cat)"

if [ -z "$workspace" ]; then
  emit deny "Define ORQUESTA_WORKSPACE con la ruta del workspace del tenant (falla cerrado)."
  exit 0
fi
if ! command -v "$engine" >/dev/null 2>&1; then
  emit deny "Motor de políticas ausente: instala orquesta (falla cerrado)."
  exit 0
fi
ref="${ORQUESTA_APPROVED_REF:-origin/main}"
sha="$(git -C "$workspace" rev-parse --verify -q "$ref^{commit}")"
if [ -z "$sha" ]; then
  emit deny "La ref aprobada $ref no existe en $workspace (falla cerrado)."
  exit 0
fi
out="$(printf '%s' "$payload" | "$engine" policy eval --hook --workspace "$workspace" --sha "$sha" 2>/dev/null)"
code=$?
if [ "$code" -ne 0 ]; then
  emit deny "El motor de políticas salió con código $code; se niega por falla cerrada."
elif [ -n "$out" ] && [[ "$out" != *'"permissionDecision"'* ]]; then
  emit deny "Respuesta ilegible del motor de políticas (falla cerrado)."
else
  printf '%s' "$out"
fi
