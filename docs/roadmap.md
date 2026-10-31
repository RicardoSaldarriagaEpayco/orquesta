# Roadmap

Cada control se exige antes de la fase que lo necesita. Las versiones se publican al cerrar cada fase.

| Fase | Entregable | Controles previos |
|---|---|---|
| **F1 Núcleo headless** | Registro por SHA, motor de políticas con adaptadores, gateway con dos proveedores y tope de costo, auditoría encadenada, evaluaciones completas, `EvidenceReceipt` firmado. CLI y librería | Identidad del operador; llave HMAC `0600` |
| **F2 Solo lectura** | LangGraph (triage, análisis de repo, revisión de PR como comentario sugerido), checkpointer Postgres, API HTTP, sandbox rootless por episodio, credencial de corta vida, OpenTelemetry | Control de salida de red; autorización por repo y entorno |
| **F3 Escritura con aprobación** | Grafo de fix: rama y diff en el sandbox, recibos, `interrupt` para push y PR vía GitHub App, QA runner con secretos | QA runner aislado; recibos verificados por hook y CI |
| **F4 Conocimiento + UI** | pgvector, interfaz web | Clasificación de datos por repo y ruta; prohibición de indexar secretos y datos regulados |
| **F5 Escala** | Modelos privados, SSO multiusuario, MCP internos, motores adicionales con traducción de activos y paridad | Alcance de datos regulados aprobado por el tenant |

## Cierre de F1 (en curso)

Ver [`specs/001-nucleo/tasks.md`](../specs/001-nucleo/tasks.md).

## LangGraph (F2)

Entra cuando haya grafos que lo usen, no antes (principio VII). Primer alcance previsto:

- Grafo de triage de solo lectura: lee el ticket por MCP, consulta el registro y el motor de políticas, pide al
  gateway la clasificación, y termina en `agent`, `ask` o `no_action`, con cada paso auditado.
- Checkpointer en Postgres (mismo servidor que la auditoría, esquema aparte).
- Nodos `interrupt` como puntos de aprobación humana, con el actor registrado.
- Las evaluaciones de F1 corren contra el grafo para medir el ruteo real (SC-004).
