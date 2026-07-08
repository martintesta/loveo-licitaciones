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
- Estado: [x] hecho. Decisión: "según el motivo". `cargar()` lee `resultados`; `ajuste_lic` da
  delta + por victorias (BONUS gana_region 5 / gana_org 6, umbral 2) y − por pérdidas 'malfit'
  (PENAL malfit 6); las 'competida' (precio/competencia) NO tocan el score. UI: ficha muestra
  ajuste verde con "+" y el panel suma VICTORIAS · región/comprador + PÉRDIDAS POR MAL FIT.
  UMBRAL_RES / PENAL / BONUS sobreescribibles desde config_local.py. Tests en test_aprendizaje.py.

## Fase C — Confianza del score visible (#1)
- Entregable: build_data expone dims evaluadas y `evaluable_pts`; la ficha y la lista muestran
  "N/6 dimensiones · M/120 evaluable" y el número se lee según su confianza.
- Listo cuando: build_data trae la confianza + se ve en la UI; tests.
- Estado: [x] hecho. build_data expone por lic `evDims`/`nDims` (dimensiones con dato real de 6) y
  `evalPts` (puntos evaluables /120). UI: badge N/6 junto al score en la lista, línea de confianza
  en el veredicto de la ficha, y conteo en el título de la card de dimensiones (tooltip explica que
  las pendientes usan neutro 5 hasta bases/cubicación). Test en test_build_data.py.
