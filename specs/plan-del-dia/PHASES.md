# PHASES: Plan del día / Next-Best-Action

## Fase 1 — Motor de acciones + panel "PLAN DE HOY"
- Entregable: `plan.construir(lics, hoy)` compone las señales en una cola priorizada de acciones con
  su porqué; build_data expone `data["plan"]` (+ `diasVisita` por lic); la UI muestra el panel
  "PLAN DE HOY" arriba del Inicio.
- Listo cuando: dado un set de licitaciones con distintos estados/deadlines, el plan las ordena
  correctamente (visita mañana arriba, cierre en 2 días con score alto arriba, etc.) con un motivo
  legible; tests puros del motor.
- Estado: [x] hecho. `plan.construir(lics)` compone las señales en una cola priorizada (valor
  score×confianza + urgencia por deadline + boost por tipo); tipos VISITA/PRESENTAR/CIERRE/CUBICAR/
  REVISAR/BASES, cada uno con su porqué; pesos/umbrales overridables. build_data expone
  `diasVisita` + `data["plan"]`. UI: panel "PLAN DE HOY" arriba del Inicio (clickeable a la ficha).
  8 tests del motor.

## Fase 2 — Push "tu plan de hoy" por email
- Entregable: el digest diario (notificar) manda el plan priorizado, no solo los deadlines sueltos.
- Listo cuando: el email trae las top-N acciones con su porqué; tests con sender inyectado.
- Estado: [ ] pendiente.

## Fase 3 — Aprender del comportamiento
- Entregable: registrar qué acciones el usuario atiende / ignora / reordena, y ajustar el ranking
  (los tipos/compradores/regiones que efectivamente ataca suben; los que ignora bajan).
- Listo cuando: tras N días de uso, el orden refleja el comportamiento real; tests.
- Estado: [ ] pendiente.

## Fase 4 — Cerrar los loops manuales
- Entregable: el recall SUGIERE la keyword con confianza (no solo la muestra); modelo de preferencia
  por usuario; recetas que agregan en vez de "última gana".
- Listo cuando: cada loop propone y el usuario solo confirma; tests.
- Estado: [ ] pendiente.
