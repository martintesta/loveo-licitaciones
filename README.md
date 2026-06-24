# loveo-licitaciones — pipeline de descubrimiento + admisibilidad + scoring + descarga + tablero

Producto interno (H1) y semilla del SaaS (H2). Local-first, "online y offline".

## El embudo (8 pasos) — estado

```
1. DESCUBRIR    → API oficial ChileCompra (diaria)          ✅ LISTO     discover.py
2. FILTRAR      → keywords límite palabra + exclusiones      ✅ LISTO     discover.py (+ aprendidas)
3. ADMISIBILIDAD→ filtro eliminatorio Loveo (regla dura)     ✅ LISTO     rules.py
4. DESCARGAR    → adjuntos vía navegador headless            ◻ CALIBRANDO download.py (corre local)
5. PUNTUAR      → provisional (API) ✅  ·  final (LLM+bases) ◻  scoring.py / Capa C
6. PRESENTAR    → tablero + acceso a documentos              ✅ LISTO     tablero.py (Streamlit)
7. FEEDBACK     → aprobar/descartar/aprender/corregir        ✅ LISTO     feedback.py
8. ESTADO       → trazabilidad doble eje + eventos + runs    ✅ LISTO     db.py
```

Orquestación: `run_daily.py` (descubrir→admisibilidad→scoring provisional, con bookkeeping en `runs`).

## Hallazgos que definen la arquitectura (probe 14-jun-2026)

| Hallazgo | Consecuencia |
|----------|--------------|
| `api.mercadopublico.cl` → 200 (CloudFront) | Descubrimiento corre donde sea. |
| El detalle de API trae todo menos los archivos | Adjuntos solo en la ficha → navegador (Capa B). |
| `www.mercadopublico.cl` → 403 a IP de datacenter | La descarga corre LOCAL (IP residencial CL). |
| Ticket de pruebas rate-limited (429) | Pedí ticket propio: api.mercadopublico.cl/modules/Participa.aspx |

## Scoring: provisional vs final (honestidad)

`scoring.py` calcula lo derivable de la API: **logístico** (distancia a la base más cercana, ×3 si >300 km),
**alineación**, **repetibilidad** y **cash flow** parcial. **Margen** y **complejidad** quedan marcados
*pendientes de bases + cubicación*. Por eso es un **score provisional para triage** (Priorizar / Revisar /
Descartar candidato), NO un GO/NO-GO. El GO/NO-GO final es la Capa C (LLM + bases + cubicación de Valentina).

Dual-base: el logístico se evalúa contra la base más cercana (Pirque + Puerto Montt). Distancias en
`scoring.py:BASES` son aproximadas — CALIBRAR.

## Estado / máquina de estados (doble eje)

```
estado_revision : nueva → en_revision → (descartada | aprobada)
estado_resultado: (si aprobada) pendiente → presentada → (ganada | perdida | desierta)
```

## Cómo correr

```bash
pip install -r requirements.txt --break-system-packages
python -m playwright install chromium

python db.py                       # crea loveo.db + ./storage
python run_daily.py 11062026       # descubrir + admisibilidad + scoring (necesita ticket propio para detalle)
python run_daily.py --backfill 5   # últimos 5 días hábiles no procesados

# Descarga de adjuntos — CORRER LOCAL (IP chilena):
python calibrate_ficha.py 2263-53-LE26   # 1) calibrar navegación a la ficha
python download.py                       # 2) bajar adjuntos de las admisibles

streamlit run tablero.py           # revisar, descargar docs, dar feedback
```

## Archivos

- `db.py` — esquema SQLite (licitaciones, documentos, eventos, runs) + helpers de estado.
- `discover.py` — Capa A: API, filtro (con exclusiones aprendidas), detalle.
- `rules.py` — admisibilidad (paso 3). No rechaza por boilerplate de ProhibicionContratacion.
- `scoring.py` — scoring Atlas provisional (paso 5a) + mapa región→distancia dual-base.
- `feedback.py` — loop de feedback (paso 7): aprobar/descartar/aprender exclusión/corregir score.
- `run_daily.py` — orquestador con bookkeeping (`runs`) y manejo de errores.
- `download.py` — Capa B (paso 4), corre local; navegación a la ficha pendiente de calibración.
- `tablero.py` — tablero Streamlit (paso 6): pipeline + acceso a documentos + feedback.
- `calibrate_ficha.py` — sonda local para fijar selectores de la ficha.
- `config_local.example.py` — plantilla: TICKET propio + keywords/umbrales (gitignored).
- `exclusiones_aprendidas.txt` — generado por feedback; lo lee discover en cada corrida.
- `docs/build_deck.js` + `docs/package.json` — generador del Documento de Producto PO/BA (versionado).

## Pendiente (post-calibración / Capa C)

- Calibrar la navegación código→ficha en `download.py` (corré `calibrate_ficha.py` local).
- Capa C: lectura de bases con Claude API → score FINAL (margen + complejidad) → GO/NO-GO.
- Mapear códigos de `TipoPago` para afinar el score de cash flow.

## Capa de datos v2 (inteligencia competitiva, desiertas, seguimiento)

Migración y módulos que llevan el tablero a data real (ver `PLAN_DATOS.md`):

- `schema_v2.py` — tablas: adjudicaciones, items, competidores, participaciones, relicitaciones.
- `extract.py` — `json_detalle` → adjudicación + items + competidores + participaciones (ganadas). Verificado: PABYMAC en 2263-53.
- `competencia.py` — `resumen()`, `ficha(rut)`, `facturado_por_anio(rut)`.
- `relicitaciones.py` — `detectar()`: enlaza desierta → re-licitación (heurístico Jaccard).
- Cableado en `run_daily.py`: `extract.extraer` tras cada upsert + `relicitaciones.detectar` al cierre.

Pendiente de segundo endpoint: perdidas (ofertas públicas), facturado exacto (OC por RUT), contacto del competidor.

## Capa C (lectura de bases con IA) — bases.py + capa_c.py

Convierte el PDF de las bases a TEXTO local y manda **solo texto** a Claude (nunca el PDF como imagen):
~1/3 de los tokens y sin tope de 100 páginas / 32 MB.

- `bases.py` — `pdf_a_texto` (pdfplumber + fallback OCR pytesseract para PDFs escaneados) y
  `texto_para_analisis` (recorta a secciones: presupuesto, plazo, garantías, evaluación, requisitos, subcontrato).
  Verificado contra un PDF real de imágenes de MP: 9 págs → OCR → 14.875 chars, 6 secciones detectadas.
- `capa_c.py` — `analizar_bases` (JSON estructurado para el score: presupuesto, plazos, garantías,
  criterios+pesos, requisitos, señales de complejidad) y `preguntar` (Q&A N3). API key SOLO del entorno
  (ANTHROPIC_API_KEY); modelo barato por defecto (Haiku). `--dry` estima tokens sin llamar a la API.

Requiere: el binario `tesseract-ocr` (+ `tesseract-ocr-spa`) para el OCR. El margen FINAL del score
sigue dependiendo de la cubicación de Valentina; Capa C aporta el techo de presupuesto y la complejidad.
