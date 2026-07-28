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
- Estado: [x] hecho. `notificar.render_plan` arma "TU PLAN DE HOY" (cola priorizada con porqué);
  `correr` lo manda cuando hay un deadline nuevo o el worker mudo (mismo disparo anti-spam). El plan
  se toma de build_data (`_plan_hoy`) y es inyectable en `correr` para tests. `--dry` muestra el
  email real. +1 test.

## Fase 3 — Aprender del comportamiento
- Entregable: registrar qué acciones el usuario atiende / ignora / reordena, y ajustar el ranking
  (los tipos/compradores/regiones que efectivamente ataca suben; los que ignora bajan).
- Listo cuando: tras N días de uso, el orden refleja el comportamiento real; tests.
- Estado: [x] hecho. Toda acción forward del usuario (seguir/aprobar/cubicar/marcar resultado…)
  registra engagement en plan_feedback (comprador/región/tipo). `plan.preferencias()` normaliza a
  pesos [0, PESO_PREF]; `construir(lics, prefs)` suma ese boost → sube lo que el usuario efectivamente
  ataca. Hook en tablero3 (`es_engagement`). 6 tests.

## Fase 4 — Cerrar los loops manuales
- Entregable: el recall SUGIERE la keyword con confianza (no solo la muestra); modelo de preferencia
  por usuario; recetas que agregan en vez de "última gana".
- Listo cuando: cada loop propone y el usuario solo confirma; tests.
- Estado: [x] hecho. Los tres loops cerrados, cada uno PROPONE y el usuario solo confirma:
  1. **Recall → keyword.** `recall.sugerencias_keywords()`: el término amplio que pescó licitaciones
     que el usuario terminó PROMOVIENDO se ofrece para subir a INCLUIR, con confianza
     (promovidas/decididas) y volumen. La UI lo muestra en el panel de recall; un click (`kw_promover`,
     admin) lo agrega y el discovery ya lo trae.
  2. **Preferencia por usuario.** `plan_feedback.usuario`; `registrar_engagement(cod, usuario)` y
     `preferencias(usuario)` aprenden del comportamiento de CADA usuario; cold-start cae al global.
     build_data recibe el usuario y sesga el plan por él.
  3. **Recetas que agregan.** `_recomputar_receta(tipo)`: la receta es el CONSENSO de todas las
     curaciones del tipo (cantidad = mediana; partida entra si aparece en ≥ la mitad), no "última gana".
     Con una sola curación equivale a copiarla (sin regresión). +8 tests.

Epic **plan-del-dia CERRADO** (4/4 fases).
