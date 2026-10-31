# ADR-0001: orquesta es un proyecto general, separado de cualquier tenant

**Fecha**: 2026-10-31 · **Estado**: aceptada

## Context

El núcleo nació para un primer tenant, con su spec, plan y tareas dentro del workspace de ese tenant y con puertas
(autorización para publicar, política de auditoría) que dependían de él.

## Decision

`orquesta` es un proyecto open source general (Apache-2.0), con su propia constitución, spec, roadmap y ADRs en este
repositorio. Cualquier tenant lo consume como dependencia desde su workspace y aporta sus datos (`workspace.yaml`,
`catalog.yaml`, `policy.yaml`, `evals/`) y sus adaptadores.

## Consequences

- Las puertas de un tenant aplican solo a sus datos: guardar su auditoría real (`ORQUESTA_AUDIT_DSN`) o enviar sus
  datasets a un modelo real requiere su propia aprobación, no frena el desarrollo del núcleo.
- `scripts/tenant_leak.py` en CI garantiza que ningún dato de tenant entre al repo; la lista de términos es un secreto
  de CI.
- Los contratos (`contracts/`) son la fuente de verdad; un tenant los cita, no los copia.
