# Constitución de orquesta

Versión 1.0.0 · Ratificada el 2026-10-31

`orquesta` es un núcleo open source (Apache-2.0) para gobernar agentes de IA de ingeniería: qué activos están
aprobados, qué puede hacer cada agente, qué quedó registrado y cómo se mide si un cambio los mejora. Cada empresa u
equipo que lo usa es un **tenant**: aporta sus datos y reglas desde su propio repositorio (*workspace*); el núcleo solo
aporta motores genéricos.

## Core Principles

### I. El tenant es dueño de sus datos; el núcleo no guarda ninguno

Agentes, skills, reglas, catálogo, datasets de evaluación y contexto viven en el workspace del tenant. El núcleo los lee
por SHA aprobado (`git show`), nunca del árbol de trabajo, y no los copia. En este repositorio no entra ningún nombre,
regla, llave ni dato de un tenant: lo verifica `scripts/tenant_leak.py` en CI con una lista de términos que vive fuera
del repo.

### II. Las políticas se aplican fuera del modelo y fallan cerradas

Toda decisión de permiso la toma código determinista con casos de prueba, no un prompt. Lo que el motor no reconoce se
niega (`unknown-input`). Un adaptador que no puede consultar al motor niega.

### III. Humano en el lazo para todo efecto externo (NON-NEGOTIABLE)

Ningún agente integra, publica, escribe en un tercero ni promueve un activo sin aprobación humana registrada. El
núcleo nunca integra su propio cambio.

### IV. Nada se da por hecho sin evidencia

Cada paso deja evidencia verificable: auditoría encadenada, recibos de pruebas por SHA, evaluaciones con línea base. Una
afirmación sin evidencia no cuenta como hecha.

### V. Los secretos nunca llegan al agente ni a los registros

Las llaves de proveedores las lee solo el gateway. La auditoría pasa por un redactor antes de escribir y no guarda
texto de prompts ni respuestas. Un canario de prueba nunca aparece en tablas, trazas ni logs.

### VI. Independencia del motor y del proveedor

Agentes y reglas se describen en formatos neutros (YAML + JSON Schema). Motores de agente y proveedores de modelo se
enchufan detrás de interfaces (`ModelProvider`, perfiles de motor) y se habilitan por allowlist del tenant.

### VII. Cambios pequeños, simples y reversibles

Nada se agrega sin un uso concreto en la fase en curso. Cada cambio entra con sus pruebas, bajo 800 líneas por PR, y se
puede revertir. Las dependencias se fijan a versión exacta.

## Restricciones de seguridad

- Single-tenant: una instalación por tenant, aislada en datos, llaves, red y auditoría.
- Sin identidad configurada, el núcleo no arranca.
- La residencia, retención y borrado de la auditoría las define cada tenant; el esquema no borra nada.
- Acciones de GitHub y contenedores fijados por SHA o digest.

## Flujo de trabajo

- Specs, planes y tareas en `specs/` con spec-kit.
- Sin comentarios en el código: los nombres explican el qué; solo se comenta un porqué no obvio.
- Sin atribución de IA en commits ni PRs.
- CI corre `ruff`, `pytest` (con Postgres real) y `tenant_leak.py` en cada PR.

## Governance

Esta constitución manda sobre cualquier otra convención del repo. Un cambio de principio exige PR propio con la razón,
versión nueva (semver) y revisión de las specs abiertas que afecte.
