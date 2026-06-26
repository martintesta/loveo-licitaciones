# PHASES: curaduría manual + aprendizaje de descartes

## Fase 1 — Alta manual por código
- Entregable: `run_daily.procesar_codigo(codigo)` (reusa detalle→upsert→admisibilidad→score)
  + input "Agregar por código" en el Listado + handler en tablero3.
- Listo cuando: `python -m pytest tests/test_manual_add.py -q` da exit 0 y se puede agregar desde la UI.
- Estado: [x] hecho

## Fase 2 — Descarte estructurado + tabla `descartes`
- Entregable: categoría de descarte en la UI (chips reales) + tabla `descartes` (schema_v3)
  + `feedback.descartar` guarda categoría/señales.
- Listo cuando: `tests/test_aprendizaje.py` verde; un descarte deja fila en `descartes`.
- Estado: [ ] pendiente

## Fase 3 — Panel de patrones + ajuste asistido del score
- Entregable: módulo `aprendizaje.py` (patrones + delta explícito) + panel "Aprendizaje" +
  nota de ajuste en la ficha/score.
- Listo cuando: una lic parecida a descartes previos muestra el ajuste con su razón; reversible.
- Estado: [ ] pendiente
