# DONE: curaduría manual + aprendizaje de descartes

- 2026-06-25 — **Fase 1 (alta manual por código) cerrada.** `run_daily.procesar_codigo()`
  reusa el pipeline diario (detalle→upsert→extract→admisibilidad→score) salteando keywords;
  input "Agregar por código" en el Listado + handler `add_codigo` en tablero3. Verificado:
  `tests/test_manual_add.py` (3 tests) verde. El reviewer adversarial encontró 1 bug real
  (scoring sin try/except → envuelto) + 1 bug en su propia herramienta (UTF-8 en subprocess de
  review/preflight en Windows → arreglado) y 3 falsos positivos (rechazados con razón).
