# DONE: analisis-integral

> Log append-only de lo cerrado. Fecha ABSOLUTA + commit + cómo se verificó.

- 2026-08-08 `c59513b` (rama `analisis-integral-y-precios`) — Fases 1-6 cerradas. El export de una licitación pasó de 2 hojas a
  8-9, todo por fórmulas encadenadas, y se guarda solo en la carpeta de bases.
  Verificado con `python scripts/preflight.py` → **394 passed, 1 skipped** (el skip es el smoke de
  Postgres, que pide `TEST_DATABASE_URL`; venía de antes).
  - El sensor fuerte es `tests/test_excel_analisis.py::test_editar_la_cantidad_recalcula_toda_la_cadena`:
    no mira que las celdas "parezcan fórmulas", las **ejecuta** con el motor `formulas` y verifica que
    duplicar la Cantidad duplique el costo base y arrastre sobrecosto, financiamiento y precio
    objetivo cruzando de hoja hasta los KPIs del Resumen.
  - Corrida real de punta a punta sobre `3761-19-LE26` (9 hojas, guardado en
    `…/Loveo Construcciones/01. Bases/3761-19-LE26/`), con la llamada a la IA inyectada para no
    gastar tokens en la verificación.
  - Bugs de la skill original arreglados al portar: formato condicional sobre rango vacío cuando no
    hay presupuesto; `SUM` con rango invertido cuando no hay cubicación ni riesgos; y el censo de
    competencia sin `p_eett` alimentando la simulación (θ=0 → "Loveo gana siempre", que es falso).
  - Pendiente: cargar `p_eett` por competidor para que la simulación use el censo real en vez de
    supuestos declarados.
