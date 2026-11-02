# Tasks: orquestación de solo lectura (F2)

**Input**: [spec.md](spec.md), [plan.md](plan.md)

Cada tarea es un PR con sus pruebas. `[P]` = puede ir en paralelo con la anterior.

## Fundación

- [x] G001 Esquema `graph` y rol `graph_writer` en `docker/initdb/20-graph.sh`; `graphs/checkpoint.py` abre `PostgresSaver` con `search_path=graph`; prueba de aislamiento entre roles (FR-050)
- [x] G002 [P] `TicketSource` y `FileTicketSource`; contrato `ticket.schema.json` (FR-061)

## US1 Triage con aprobación

- [ ] G003 Grafo de triage: nodos `load`, `resolve`, `classify`, `policy`, `approve` (`interrupt`), `finish`; contrato `triage-result.schema.json`; eventos `graph.step` y `approval` (FR-051 a FR-054)
- [ ] G004 CLI `orquesta triage start|status|resume`; reanudar tras reiniciar el proceso sin repetir nodos (SC-010)
- [ ] G005 `eval run --engine graph`: la suite de ruteo pasa por el grafo (SC-004)

## US2 API HTTP

- [ ] G006 `api/auth.py`: tokens con hash en archivo `0600`, roles `viewer`/`operator`/`approver` por repo, evento `authz` (FR-056)
- [ ] G007 `api/app.py`: `/v1/policy/eval`, `/v1/registry`, `/v1/runs`, `/v1/runs/{id}`, `/v1/runs/{id}/resume`, `/healthz`; `orquesta serve` en `127.0.0.1`; paridad con el CLI; `contracts/api.md` (FR-055, FR-057)

## US3 Episodio aislado

- [ ] G008 `gateway/credential.py`: credencial de episodio firmada, `exp` ≤ 15 min, ligada a corrida, modelos y presupuesto; `POST /v1/models/complete` la exige (FR-060, SC-012)
- [x] G009 [P] `sandbox/egress.py`: proxy `CONNECT` con allowlist exacta y evento `egress` (FR-059, SC-011)
- [ ] G010 `sandbox/runner.py`: contenedor rootless efímero sin capacidades, red interna solo hacia el proxy, limpieza garantizada (FR-058)

## US4 Análisis y revisión

- [ ] G011 Grafo de análisis de repo: clon dentro del sandbox, informe como salida
- [ ] G012 Grafo de revisión de PR: comentario sugerido como salida, sin publicar (SC-013)
- [ ] G013 [P] `McpTicketSource` configurado en `workspace.yaml` del tenant

## US5 Observabilidad y cierre

- [ ] G014 `telemetry.py`: spans por nodo y por petición, redactor, exportación OTLP opcional; prueba de canario (FR-062, SC-007)
- [ ] G015 Documentación: arquitectura, roadmap, README, `examples/` con una corrida de triage en `demo.sh`
- [ ] G016 Versión `0.2.0` al cerrar la fase, cuando el dueño lo indique

## Dependencies

G003 depende de G001 y G002. G004, G005 y G007 dependen de G003. G007 depende de G006. G010 depende de G009. G011 y
G012 dependen de G008 y G010. G014 puede entrar después de G003.
