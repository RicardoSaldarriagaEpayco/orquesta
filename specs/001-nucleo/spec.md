# Feature Specification: núcleo de orquesta

**Feature Branch**: `001-nucleo` | **Created**: 2026-10-31 | **Status**: F1 en cierre

**Input**: gobernar agentes de IA de ingeniería que hoy corren en un cliente de agentes (Claude Code) con reglas en
hooks de bash, activos en un repo y evidencia local sin firmar. El núcleo convierte eso en motores genéricos que
cualquier tenant consume desde su workspace.

## Contexto

- **Tenant**: equipo o empresa que usa `orquesta`. Su workspace (repo git) guarda agentes y skills en `.claude/`,
  `workspace.yaml` (portafolio de repos), `catalog.yaml` (gobierno de activos), `policy.yaml` (reglas y modelos
  permitidos) y `evals/` (suites).
- **Operador**: persona que corre el núcleo para su tenant. En F1, en su máquina, con su identidad personal.
- **Motor de agente**: Claude Code hoy; Codex, OpenCode o un bucle propio mañana. Ejecuta un paso acotado.
- **Adaptador**: hook del cliente, job de CI o la plataforma; traduce su entrada al motor de políticas.

## User Scenarios & Testing

### User Story 1 - Activos aprobados por SHA (P1)

Como responsable del workspace quiero que agentes y skills se resuelvan desde un commit aprobado, con su catálogo y un
digest, para que lo que corre sea exactamente lo revisado.

1. **Given** un SHA alcanzable desde la rama aprobada, **When** se lista el registro, **Then** cada activo trae
   frontmatter, entrada de catálogo y `digest`, y valida contra `contracts/agent-asset-manifest.schema.json`.
2. **Given** un activo con frontmatter roto o sin entrada de catálogo, **When** se lista, **Then** sale `AssetError`
   con activo y campo, código `4`.
3. **Given** un lock aprobado, **When** un activo cambia en un commit nuevo, **Then** `registry verify` sale con `6`.

### User Story 2 - Una sola política para todos los puntos de entrada (P1)

1. **Given** las reglas de `policy.yaml` y `workspace.yaml` del SHA aprobado, **When** un adaptador consulta, **Then**
   recibe `allow`, `deny` o `ask` con `rule_id`, en menos de 300 ms.
2. **Given** una entrada que ninguna regla sabe evaluar, **When** se consulta, **Then** `deny` con `unknown-input`.
3. **Given** el mismo caso en dos adaptadores, **When** se corre el fixture de paridad, **Then** ambos dan el mismo
   veredicto.

### User Story 3 - Gateway de modelos y auditoría encadenada (P1)

1. **Given** un modelo fuera de la allowlist del tenant, **When** se pide, **Then** `ModelNotAllowed` sin llamada.
2. **Given** eventos en la auditoría, **When** se altera o borra uno intermedio, **Then** `audit verify` sale con `7`
   y el `seq` roto.
3. **Given** un secreto canario en un evento, **When** se escribe, **Then** no aparece en la tabla ni en logs.

### User Story 4 - Evaluar el comportamiento de los agentes (P2)

1. **Given** una suite con el resultado esperado por caso, **When** corre, **Then** reporta exactitud total y por
   proyecto, `ask_recall` y `no_action_respected`, y lo esperado nunca entra al prompt.
2. **Given** una línea base, **When** corre un candidato, **Then** el `PromotionRecord` lista las regresiones fuera del
   margen y queda pendiente de aprobación humana.

### User Story 5 - Evidencia firmada del trabajo (P2)

1. **Given** una puerta de calidad que pasó sobre un commit, **When** se emite su recibo, **Then** el recibo
   (`EvidenceReceipt`) trae SHA, comando, versión, resultado y fecha, firmado, y vence si cambia el input.
2. **Given** un PR, **When** se evalúa `pr-without-receipt`, **Then** se acepta solo un recibo firmado vigente.

### User Story 6 - Elegir motor y proveedor por política (P3, F2 en adelante)

Ejecutar cada paso con el motor y el proveedor que la política indique, con los mismos activos traducidos por
generación y paridad verificada.

## Requirements

### Registro

- **FR-019**: El registro MUST leer activos solo con `git show <sha>:<ruta>` de un SHA alcanzable desde la rama
  aprobada; nunca del árbol de trabajo.
- **FR-020**: Cada activo MUST tener entrada en `catalog.yaml` con dueño, origen, licencia (si es de terceros, con
  commit completo), clasificación, salida de red, efectos externos, evaluaciones, vencimiento y aprobaciones.
- **FR-021**: Rutas fuera de `.claude/` o con `..` MUST rechazarse.
- **FR-022**: Un activo con efectos externos MUST declarar `disable-model-invocation: true`.
- **FR-024**: Promover un conjunto MUST exigir el SHA vigente esperado (concurrencia optimista) y permitir rollback.

### Políticas

- **FR-025**: Un solo motor MUST decidir; los adaptadores no tienen lógica de decisión.
- **FR-026**: El motor MUST fallar cerrado ante entrada ilegible (`2`), reglas ilegibles o SHA no aprobado (`3`).
- **FR-027**: Las reglas MUST leerse del SHA aprobado.

### Auditoría

- **FR-028**: Cada decisión, resolución, llamada a modelo, corrida de evaluación y promoción MUST registrar un evento
  con actor, tenant, SHA de política y de activos, decisión, latencia y referencias.
- **FR-029**: La escritura MUST ser de solo anexado para el rol que escribe; la cadena HMAC detecta alteraciones.
- **FR-030**: Prompts y respuestas MUST NOT guardarse; `refs` y `decision` pasan por el redactor.
- **FR-030a**: Residencia, retención y borrado los define cada tenant; el núcleo no borra eventos.

### Gateway y costo

- **FR-037**: Las llaves de proveedores MUST quedar en el gateway; desde F2 el episodio recibe una credencial de corta
  vida.
- **FR-038**: El gateway MUST rechazar proveedores y modelos fuera de la allowlist del tenant.
- **FR-039**: El gateway MUST registrar costo por llamada y MUST detener la ejecución cuando un presupuesto del tenant
  se agota.
- **FR-039a**: El gateway MUST soportar al menos dos proveedores reales detrás de `ModelProvider`.

### Evaluaciones

- **FR-031**: Una suite MUST declarar corridas, motor, límite de tiempo, herramientas permitidas y casos; los
  evaluadores cubren ruteo, uso de herramientas, patrón en el mensaje final y recibos esperados.
- **FR-033**: Lo esperado MUST NOT entrar al contexto del agente evaluado.

### Evidencia

- **FR-046**: Los recibos de las puertas de calidad MUST firmarse, ligarse al SHA y a los insumos, y vencer cuando
  cambian.

### Identidad, tenancy y núcleo abierto

- **FR-043**: Sin identidad configurada, el núcleo MUST NOT arrancar.
- **FR-044**: Una instalación por tenant, aislada en datos, llaves, red y auditoría.
- **FR-045**: El repo MUST NOT contener datos, nombres, reglas ni llaves de ningún tenant; lo verifica CI.

## Success Criteria

- **SC-004**: El ruteo acierta al menos el 90% de una suite real y pregunta en el 100% de los casos ambiguos.
- **SC-006**: El 100% de las alteraciones inyectadas en la auditoría se detecta.
- **SC-007**: Un canario aparece 0 veces en registros, trazas o almacenamiento.
- **SC-008**: Las puertas de política dan el mismo veredicto en el 100% de los casos en todos los adaptadores.
- **SC-009**: Ningún cambio de activo entra en uso sin evaluación y aprobación registradas; un rollback deja la
  versión anterior operativa en menos de 5 minutos.

## Out of Scope (F1)

Servidor HTTP, LangGraph, sandbox de episodios, OIDC y GitHub App, conocimiento indexado e interfaz web: ver
[`docs/roadmap.md`](../../docs/roadmap.md).
