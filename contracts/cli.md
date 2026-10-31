# Contrato: CLI `orquesta`

Toda salida `--json` es estable y la reutilizará la API HTTP de F2. Ningún comando escribe en el workspace del tenant
ni en sus repos; solo leen por `git show` y escriben en la base de auditoría o en la ruta de salida indicada.

| Comando | Qué hace | Códigos |
|---|---|---|
| `registry list --workspace <ruta> --sha <sha> [--json]` | Resuelve agentes y skills en ese SHA (frontmatter + `catalog.yaml`) | `0` · `4` activo inválido · `5` SHA no alcanzable |
| `registry lock --workspace <ruta> --sha <sha>` | Calcula el lock `asset_id → digest` como `ApprovedSet` candidato | `0` · `4` · `5` |
| `registry verify --workspace <ruta> --lock <archivo>` | Recalcula digests y compara | `0` · `6` difiere |
| `policy eval --workspace <ruta> --sha <sha> [--hook]` | Evalúa un `PolicyRequest` de stdin ([policy-decision.md](policy-decision.md)) | `0` · `2` · `3` |
| `policy test --workspace <ruta> --sha <sha> --fixtures <archivo>` | Corre un fixture de paridad con las reglas del SHA | `0` · `1` algún caso difiere |
| `audit verify` | Recorre la cadena HMAC | `0` · `7` cadena rota · `9` sin llave o sin base |
| `eval run --workspace <ruta> --suite <ruta-en-workspace> --sha <sha> --provider fake\|anthropic [--answers <tabla>] [--baseline <EvalRun>] [--record <ruta>]` | Corre una suite de ruteo y, con `--record`, escribe el `PromotionRecord` | `0` · `8` suite inválida |

## Errores tipados

`AssetError(asset_id, field, reason)`, `ShaNotApproved(sha)`, `LockMismatch(differences)`, `AuditChainBroken(seq)`,
`AuditKeyInsecure(path, reason)`, `ModelNotAllowed(provider, model)`, `ProviderNotAllowed(provider)`,
`ProviderError(provider, reason)`, `SuiteInvalid(suite, reason)`. Se imprimen como JSON en stderr con `--json` y como
una línea legible sin él.

## Entorno

| Variable | Uso |
|---|---|
| `ORQUESTA_ACTOR` | Identidad del operador; si falta, la de `gh auth status`. Sin ninguna, el núcleo no arranca |
| `ORQUESTA_AUDIT_DSN` | Credencial de `audit_writer`. Si no está, ningún comando escribe auditoría |
| `ORQUESTA_AUDIT_KEY` | Ruta de la llave HMAC (por defecto `~/.config/orquesta/audit.key`, permisos `0600`) |
| `ORQUESTA_ENTRYPOINT` | `entrypoint` del `PolicyRequest` en modo `--hook` (por defecto `claude-wsl`) |
| `ANTHROPIC_API_KEY` | Llave del proveedor; la lee solo el gateway |
