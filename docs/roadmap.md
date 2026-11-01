# Roadmap

Cada control se exige antes de la fase que lo necesita. Las versiones se publican al cerrar cada fase.

| Fase | Entregable | Controles previos |
|---|---|---|
| **F1 Núcleo headless** | Registro por SHA, motor de políticas con adaptadores, gateway con dos proveedores y tope de costo, auditoría encadenada, evaluaciones completas, `EvidenceReceipt` firmado. CLI y librería | Identidad del operador; llave HMAC `0600` |
| **F2 Solo lectura** | LangGraph (triage, análisis de repo, revisión de PR como comentario sugerido), checkpointer Postgres, API HTTP, sandbox rootless por episodio, credencial de corta vida, OpenTelemetry | Control de salida de red; autorización por repo y entorno |
| **F3 Escritura con aprobación** | Grafo de fix: rama y diff en el sandbox, recibos, `interrupt` para push y PR vía GitHub App, QA runner con secretos | QA runner aislado; recibos verificados por hook y CI |
| **F4 Conocimiento + UI** | pgvector, interfaz web | Clasificación de datos por repo y ruta; prohibición de indexar secretos y datos regulados |
| **F5 Escala** | Modelos privados, SSO multiusuario, MCP internos, motores adicionales con traducción de activos y paridad | Alcance de datos regulados aprobado por el tenant |

## Cierre de F1

Hecho salvo la versión `0.1.0`: ver [`specs/001-nucleo/tasks.md`](../specs/001-nucleo/tasks.md).

## F2 (en curso)

Spec, plan y tareas en [`specs/002-solo-lectura/`](../specs/002-solo-lectura/). Primer entregable: grafo de triage de
solo lectura con checkpointer Postgres en esquema propio y aprobación por `interrupt`, servido por CLI y API HTTP.
