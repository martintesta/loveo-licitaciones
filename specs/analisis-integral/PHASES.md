# PHASES: analisis-integral

> Estado: [ ] pendiente · [~] en curso · [x] hecho.

## Fase 1 — OCR que no falla en silencio
- Entregable: `bases.tesseract_exe()` / `ocr_disponible()`; `_ocr_pagina` apunta pytesseract al
  binario real. Env var `LOVEO_TESSERACT` para forzarlo.
- Listo cuando: `python -m pytest tests/test_digest.py -q` da exit 0
- Estado: [x]

## Fase 2 — Digest de bases
- Entregable: `digest.py` — `extracto(codigo)` (reusa `bases.documento_a_texto`, con caché y OCR) y
  `digerir(texto)` con las 16 reglas que el análisis financiero/estratégico necesita.
- Listo cuando: `python -m pytest tests/test_digest.py -q` da exit 0
- Estado: [x]

## Fase 3 — Datos del análisis (determinista + IA)
- Entregable: `analisis.py` — `datos(codigo, enriquecer=None)`. Parámetros del modelo financiero
  como fuente única (`PARAMS`, `FACTOR_SANO`, `FACTOR_LIMITE`), cubicación preciada desde
  `precios_referencia`, censo desde la base, y UNA llamada a Claude con structured outputs.
- Listo cuando: `python -m pytest tests/test_analisis.py -q` da exit 0
- Estado: [x]

## Fase 4 — Excel de 8-9 hojas con fórmulas vivas
- Entregable: `excel_analisis.py` — `construir(D)`. Cadena costo→precio encadenada, escenarios,
  P&L, KPIs, matriz de evaluación + Monte Carlo + minimax regret, censo.
- Listo cuando: `python -m pytest tests/test_excel_analisis.py -q` da exit 0 **con el motor de
  fórmulas instalado** (`pip install -r requirements-dev.txt`)
- Estado: [x]

## Fase 5 — Orquestación y guardado
- Entregable: `informe.generar(codigo)` — arma, guarda en la carpeta de bases y devuelve bytes;
  `tablero3.py` muestra dónde quedó y si corrió la IA.
- Listo cuando: `python -m pytest tests/test_informe.py -q` da exit 0
- Estado: [x]

## Fase 6 — Consolidado multi-licitación
- Entregable: `consolidado.py` — tablero de decisión del lote vigente, con techos de costo y
  semáforo como fórmulas, más info faltante y descartes.
- Listo cuando: `python -m pytest tests/test_analisis.py -q` da exit 0
- Estado: [x]
