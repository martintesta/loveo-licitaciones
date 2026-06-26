# DONE: curaduría manual + aprendizaje de descartes

- 2026-06-25 — **Fase 1 (alta manual por código) cerrada.** `run_daily.procesar_codigo()`
  reusa el pipeline diario (detalle→upsert→extract→admisibilidad→score) salteando keywords;
  input "Agregar por código" en el Listado + handler `add_codigo` en tablero3. Verificado:
  `tests/test_manual_add.py` (3 tests) verde. El reviewer adversarial encontró 1 bug real
  (scoring sin try/except → envuelto) + 1 bug en su propia herramienta (UTF-8 en subprocess de
  review/preflight en Windows → arreglado) y 3 falsos positivos (rechazados con razón).
- 2026-06-25 — **Fase 2 (descarte estructurado) cerrada.** Tabla `descartes` (schema_v3) +
  `feedback.CATEGORIAS` con dos tipos (calidad alimenta el score / operativo no lo toca:
  visita_perdida, sin_capacidad) + UI con chips de categoría (desde el backend, sin duplicar
  en JS). Verificado: `tests/test_aprendizaje.py` (4) verde. Reviewer: 1 fix aplicado (sacar
  migrate() del hot-path del descarte), 3 falsos positivos rechazados (AUTOINCREMENT/conexión
  cacheada los traduce/maneja el proyecto) + nota al prompt para no repetir el FP de AUTOINCREMENT.
- 2026-06-25 — **Fase 3 (ajuste asistido + panel) cerrada → #2 COMPLETO.** Módulo `aprendizaje.py`
  (carga DB separada de la lógica pura `ajuste_lic`): solo descartes de calidad atribuibles
  (muy_lejos→región, mal_pagador→comprador) sobre umbral 3 ajustan el score, con razón explícita;
  operativos nunca penalizan; visita_perdida solo alerta. Enganchado en `build_data` (1 carga,
  display-only por lic) + panel "Aprendizaje" en el rail + tarjeta de ajuste en la ficha.
  Verificado: `tests/test_aprendizaje.py` (8) verde. Reviewer: 1 fix (capear score ajustado en 0
  para no mostrar negativos); el resto se auto-rechazó como no-bug.
