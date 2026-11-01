# Tasks: núcleo de orquesta (F1)

**Input**: [spec.md](spec.md), [docs/architecture.md](../../docs/architecture.md), [contracts/](../../contracts/)

## Hecho

- [x] N001 Esqueleto: `pyproject.toml` con versiones exactas, `uv.lock`, CLI que no arranca sin identidad (FR-043), errores tipados, lectura del workspace por SHA (FR-019), `tenant_leak.py` y CI (FR-045)
- [x] N002 [US1] Registro: `AgentAssetManifest`, resolución por `git ls-tree`, digest, `ApprovedSet` con promoción optimista y rollback (FR-019 a FR-024)
- [x] N003 [US2] Motor de políticas: 7 reglas más `unknown-input`, `Environment`, fixture de paridad, `policy eval` y `policy test` (FR-025 a FR-027)
- [x] N004 [US2] Modo `--hook` y ruta caliente bajo 300 ms
- [x] N005 [US3] Gateway: `ModelProvider`, `FakeProvider`, `AnthropicProvider` sin red en pruebas, allowlist (FR-037, FR-038)
- [x] N006 [US3] Auditoría: Postgres con roles, cadena HMAC, redactor, llave `0600`, `audit verify`, eventos de `policy eval`, `registry` y `eval run` (FR-028 a FR-030)
- [x] N007 [US4] Evaluaciones de ruteo: suites, corrida por mayoría, métricas, `PromotionRecord` (FR-031, FR-033)
- [x] N008 Separación del tenant: constitución, spec, roadmap, ADR-0001 y contratos en este repo

## Cierre de F1

- [x] N009 [P] [US3] Segundo proveedor real detrás de `ModelProvider`: `OpenAICompatibleProvider` para servidores con la API de OpenAI (vLLM, Ollama, gateways privados), probado sin red (FR-039a)
- [x] N010 [US3] Tope de costo: presupuesto por tenant y por corrida en el gateway; al agotarse, `BudgetExceeded` antes de llamar, con evento auditado (FR-039)
- [x] N011 [P] [US5] `EvidenceReceipt`: contrato JSON Schema, firma Ed25519 con llave del operador, `orquesta receipt sign|verify`, vencimiento por cambio de insumos (FR-046)
- [x] N012 [US5] `pr-without-receipt` acepta recibos firmados vigentes además del marcador local
- [x] N013 [P] [US4] Evaluadores restantes de FR-031: uso de herramientas, patrón en el mensaje final y recibos esperados, con métricas propias
- [x] N014 [US2] Job de CI de paridad: corre `tests/policy/fixtures.yaml` contra el motor y contra un adaptador de hook de ejemplo (SC-008)
- [x] N015 Publicar el repo con CI activa y el secreto `TENANT_TERMS_FILE`; README con guía de integración para un tenant
- [x] N016 Correr de punta a punta: registro, política y evaluación contra un workspace de ejemplo genérico en `examples/` (`demo.sh`, probado en CI)
- [ ] N017 Versión `0.1.0` al cerrar la fase, cuando el dueño lo indique

## Dependencies

N009 y N011 son independientes. N010 depende de N009 (precios por proveedor). N012 depende de N011. N014 y N016
dependen de N015.
