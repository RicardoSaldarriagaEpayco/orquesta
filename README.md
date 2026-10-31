# orquesta

Núcleo para gobernar agentes de IA de ingeniería en una empresa: qué agentes y skills están aprobados, qué puede
hacer cada uno, qué quedó registrado y cómo se mide si un cambio los mejora o los empeora.

Complementa a Claude Code; no lo reemplaza. Los agentes, skills y reglas de cada empresa viven en el repo de esa
empresa (su *workspace*). `orquesta` solo trae los motores genéricos y lee el workspace por SHA, nunca del árbol de
trabajo.

## Qué hace

| Módulo | Para qué |
|---|---|
| `registry` | Resuelve los agentes y skills de un SHA aprobado del workspace, con su catálogo y un digest por activo, y los fija en un lock |
| `policy` | Decide `allow`, `deny` o `ask` para cada acción de un agente con las reglas del workspace, y niega lo que no reconoce |
| `audit` | Guarda cada decisión en una cadena HMAC de solo anexado y verifica que nadie la alteró |
| `gateway` | Llama a los modelos permitidos por la empresa y registra proveedor, modelo, latencia y costo, sin el texto |
| `evals` | Corre suites de casos contra un conjunto de activos y compara contra la línea base antes de promoverlo |

## Reglas del repo

- Sin datos de ninguna empresa: ni nombres de repos, ni llaves, ni reglas, ni contexto. Los datos de prueba son
  genéricos y una puerta de CI lo verifica.
- Una instalación por empresa (single-tenant), aislada en datos, llaves, red y auditoría.
- Sin identidad configurada, `orquesta` no arranca.

## Estado

En construcción. Todavía no hay código ni versión publicada.

## Licencia

[Apache-2.0](LICENSE).
