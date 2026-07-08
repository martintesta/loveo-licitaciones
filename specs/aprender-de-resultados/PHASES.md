# PHASES: aprender de resultados + score honesto

## Fase A — Resultado con motivo estructurado (#4)
- Entregable: al marcar ganada/perdida, elegir una categoría de motivo. Se guarda en `resultados`
  (schema_v3). Categorías propuestas:
    - Ganada: `precio_competitivo`, `unico_oferente`, `buena_relacion`, `otro`
    - Perdida: `precio`, `competencia_fuerte`, `requisito`, `plazo`, `mal_fit`, `otro`
- UI: el form de "marcar resultado" en la ficha pide la categoría (chips, como descartes).
- Listo cuando: `tests/test_resultados.py` verde; marcar resultado deja fila con categoría.
- Estado: [x] hecho (backend + UI: form de motivo en la ficha al marcar ganada/perdida)

## Fase B — Aprendizaje de resultados (#2)
- Entregable: `aprendizaje.py` suma señal de VICTORIAS (por región/organismo → sube el score de
  parecidas) y trata las PÉRDIDAS según la decisión de producto. Peso por confianza (cantidad).
- Regla: display-only, explícito, reversible. Operativo/competencia no castigan el fit.
- Listo cuando: test de que una racha de ganadas sube y las pérdidas ajustan según motivo.
- Estado: [ ] pendiente (bloqueada por la decisión de producto)

## Fase C — Confianza del score visible (#1)
- Entregable: build_data expone dims evaluadas y `evaluable_pts`; la ficha y la lista muestran
  "N/6 dimensiones · M/120 evaluable" y el número se lee según su confianza.
- Listo cuando: build_data trae la confianza + se ve en la UI; tests.
- Estado: [ ] pendiente
