# Feature Specification: orquestación de solo lectura (F2)

**Feature Branch**: `002-solo-lectura` | **Created**: 2026-11-01 | **Status**: borrador

**Input**: F1 dejó motores sueltos (registro, política, gateway, auditoría, evaluaciones, recibos) que se llaman por
CLI. F2 los encadena en grafos con estado durable, pausas de aprobación humana y una API HTTP, sin que ningún agente
escriba fuera de su sandbox.

## Contexto

- **Grafo**: flujo de LangGraph cuyos nodos llaman a los motores de F1. Su estado vive en un checkpointer Postgres;
  un nodo `interrupt` pausa la corrida hasta que una persona responde.
- **Corrida** (`run`): una ejecución de un grafo, identificada por `run_id` (el `thread_id` de LangGraph).
- **Episodio**: el trabajo de un agente dentro de una corrida, en un contenedor efímero que solo sale a la red por un
  proxy con allowlist y que recibe una credencial de corta vida en lugar de llaves.
- **Fuente de tickets**: de dónde sale el ticket a triar. Un archivo en pruebas; un servidor MCP del tenant en uso real.
- **Roles**: `viewer` (lee), `operator` (inicia corridas), `approver` (responde interrupciones). Se asignan por
  repo del `workspace.yaml`.

## User Scenarios & Testing

### User Story 1 - Triage de un ticket con aprobación (P1)

Como operador quiero que un ticket se clasifique en `agent`, `ask` o `no_action` con el agente propuesto, y que una
persona confirme antes de darlo por ruteado.

1. **Given** un ticket y un SHA aprobado, **When** inicio el triage, **Then** el grafo resuelve los agentes del
   registro, pide la clasificación al gateway, consulta la política y se pausa en `approve` con la propuesta.
2. **Given** una corrida pausada, **When** un `approver` responde `approve` o `reject`, **Then** la corrida termina
   con `TriageResult` y un evento `approval` con su identidad.
3. **Given** una corrida pausada y el proceso reiniciado, **When** se consulta o se responde, **Then** continúa desde
   el checkpoint sin repetir pasos.
4. **Given** una clasificación `ask` o una decisión de política `deny`, **When** termina, **Then** no se propone
   ningún agente.

### User Story 2 - API HTTP con autorización (P1)

1. **Given** un token válido con rol `operator` en el repo del ticket, **When** llama `POST /v1/runs`, **Then** la
   corrida inicia y responde su `run_id`.
2. **Given** un token sin el rol o sin el repo, **When** llama, **Then** `403` y un evento `authz` con `deny`.
3. **Given** la salida JSON de un comando del CLI, **When** se pide lo mismo a la API, **Then** el cuerpo es igual.

### User Story 3 - Episodio aislado (P1)

1. **Given** un episodio, **When** intenta salir a un host fuera de la allowlist, **Then** la conexión se niega y se
   audita `egress` con `deny`.
2. **Given** un episodio, **When** llama al gateway, **Then** usa una credencial que vence en minutos, ligada a la
   corrida, al presupuesto y a los modelos permitidos; las llaves del proveedor nunca entran al contenedor.
3. **Given** un episodio terminado, **When** se revisa el host, **Then** no queda contenedor, volumen ni clon.

### User Story 4 - Análisis de repo y revisión de PR sugerida (P2)

1. **Given** un repo con `write: true` o `false`, **When** se analiza, **Then** el clon vive solo en el sandbox y la
   salida es un informe; nada se empuja ni se comenta.
2. **Given** un PR, **When** se revisa, **Then** la salida es un comentario sugerido que una persona decide publicar.

### User Story 5 - Medir el ruteo real y trazar (P2)

1. **Given** una suite de ruteo, **When** corre con `--engine graph`, **Then** cada caso pasa por el grafo de triage
   con aprobación automática de prueba y produce las métricas de F1 (SC-004).
2. **Given** una corrida, **When** se exportan trazas, **Then** hay un span por nodo y por petición HTTP, sin texto de
   prompts, respuestas ni secretos.

## Requirements

### Grafos y estado

- **FR-050**: Los grafos MUST usar un checkpointer Postgres en un esquema propio (`graph`) del mismo servidor de la
  auditoría, con un rol que no lee ni escribe el esquema de auditoría.
- **FR-051**: Toda aprobación MUST ser un nodo `interrupt`; reanudar exige un actor con rol `approver` y queda
  auditado con ese actor.
- **FR-052**: Cada nodo MUST emitir un evento de auditoría `graph.step` con `run_id`, nodo, resultado y latencia,
  sin texto del ticket ni del modelo.
- **FR-053**: Los nodos MUST llamar a los motores de F1 como librería; no hay lógica de política ni de registro
  duplicada en el grafo.
- **FR-054**: En F2 ningún nodo MUST tener efectos fuera del sandbox ni de la base: sin push, sin comentarios, sin
  escrituras en el tracker.

### API

- **FR-055**: La API MUST exponer política, registro, corridas (iniciar, consultar, reanudar) y llamadas al gateway
  con la misma forma JSON que el CLI.
- **FR-056**: Cada petición MUST autenticarse con un token que mapea a un actor y a roles por repo; los tokens se
  guardan solo como hash en un archivo `0600` del operador. Sin token válido, `401`.
- **FR-057**: La API MUST escuchar en `127.0.0.1` por defecto; exponerla es decisión explícita del operador.

### Sandbox y credenciales

- **FR-058**: Cada episodio MUST correr en un contenedor rootless efímero, sin capacidades, con sistema de archivos
  de solo lectura salvo un directorio de trabajo temporal, y destruirse al terminar.
- **FR-059**: La única salida de red del episodio MUST ser un proxy que permite solo los hosts del tenant y del
  gateway, y audita cada conexión negada.
- **FR-060**: El episodio MUST recibir una credencial firmada con vencimiento de 15 minutos o menos, limitada a su
  corrida, modelos y presupuesto. El gateway la valida y nunca la acepta vencida o de otra corrida.

### Fuentes y observabilidad

- **FR-061**: La fuente de tickets MUST ser una interfaz; F2 trae una de archivo y una de cliente MCP configurada en
  el `workspace.yaml` del tenant.
- **FR-062**: Las trazas MUST seguir OpenTelemetry, con exportación configurable y apagada por defecto, y pasar por el
  redactor de la auditoría.

## Success Criteria

- **SC-010**: El 100% de las corridas interrumpidas y reanudadas tras reiniciar el proceso termina sin repetir nodos.
- **SC-011**: El 100% de los intentos de salida a hosts fuera de la allowlist se niega y queda auditado.
- **SC-012**: Una credencial vencida o de otra corrida se rechaza el 100% de las veces.
- **SC-013**: Ningún agente produce efectos externos en F2: 0 push, 0 comentarios, 0 escrituras en terceros.
- **SC-004** y **SC-007** de F1 se miden ahora contra el grafo.

## Out of Scope (F2)

Escritura con aprobación, GitHub App, QA runner (F3); conocimiento indexado e interfaz web, OIDC (F4); SSO y
modelos privados (F5).
