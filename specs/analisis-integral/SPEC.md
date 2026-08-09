# SPEC: analisis-integral

## Problema

El export de una licitación eran 2 hojas (Resumen + Cubicación): alcanza para mirar, no para
decidir. Todo lo que de verdad decide un GO/NO-GO — el plan de compras, los riesgos con su costo de
mitigación, quién hace qué, y sobre todo **cómo se reparte el puntaje de la matriz de evaluación** —
vivía en una skill externa (`analizar-licitacion`) que corría a mano, fuera del pipeline, contra un
JSON escrito a mano. Resultado: el análisis bueno existía pero no era reproducible, no quedaba
guardado junto a las bases, y podía contradecir al tablero.

Además, 8 de 25 licitaciones de un lote real tenían el PDF de bases como **escaneo sin capa de
texto**. El OCR estaba implementado pero fallaba en silencio: en Windows el instalador de Tesseract
no toca el PATH, `pytesseract` tiraba `TesseractNotFoundError`, el except se lo tragaba y la
licitación quedaba sin texto. Inanalizable, sin ningún error visible.

## Objetivo

Que `informe.py` produzca el análisis integral completo (8-9 hojas, todo por fórmulas encadenadas)
dentro del pipeline, y lo deje guardado en la carpeta de bases de la licitación.

## Alcance

- **Incluye**: extracción de todas las bases con OCR real · digest de 16 secciones · UNA llamada a
  Claude para lo que la base no tiene · Excel de 8-9 hojas con fórmulas vivas · guardado automático
  en la carpeta de bases · consolidado multi-licitación.
- **NO incluye** (explícito): re-analizar bases que la Capa C ya leyó (se reusa su extracción) ·
  inventar precios (la cubicación se precia contra `precios_referencia`) · hacer viva la simulación
  Monte Carlo (es estática y la hoja lo dice en rojo).

## Decisiones

1. **Híbrido, no "todo IA"**: lo determinista sale de la base (mismo origen que el tablero, así el
   Excel no puede contradecir a la UI); la IA solo aporta lo que no está en ninguna tabla. Una sola
   llamada, con structured outputs (el schema lo valida la API: no hay que parsear ni reintentar).
2. **Un solo botón**: el export del tablero pasa a ser siempre el análisis integral. Se paga el
   costo de leer bien una vez, en vez de mantener dos caminos.
3. **La cubicación curada MANDA**: si hay BOM del usuario/Valentina, la propuesta de la IA se
   descarta. Los precios salen del catálogo real (91 precios de Loveo), nunca de lo que el modelo
   recuerde.
4. **Degradar, no morir**: sin API key, sin red o con JSON ilegible el informe igual sale, con las
   hojas que sí tienen datos, y lo dice en INFO FALTANTE.

## Criterios de aceptación

- [x] Genera 8-9 hojas con las piezas del análisis → `python -m pytest tests/test_informe.py -q`
- [x] Editar Cantidad en Cubicación recalcula la cadena hasta los KPIs del Resumen, **ejecutando las
      fórmulas** con un motor real → `python -m pytest tests/test_excel_analisis.py -q`
- [x] La cubicación se precia desde `precios_referencia`, y lo que no está se reporta como faltante
      → `python -m pytest tests/test_analisis.py -q`
- [x] El digest captura lo que decide la estrategia y está acotado → `python -m pytest tests/test_digest.py -q`
- [x] El Excel queda SIEMPRE en la carpeta de bases de la licitación → `tests/test_informe.py::test_siempre_guarda_en_la_carpeta_de_bases`
- [x] Sin regresiones → `python scripts/preflight.py`

## Invariantes respetados

- **El score es provisional**: el informe lee `score_json`, no recalcula nada por su cuenta; el
  veredicto sale de `scoring.triage` (una sola fuente con el tablero).
- **Postgres vs SQLite**: todo el SQL nuevo pasa por `db.conn()`, sin `lastrowid`, y los conteos de
  booleanos usan `SUM(CASE WHEN ... THEN 1 ELSE 0 END)`.
- **Secretos**: la API key sale del entorno (o `config_local.API_KEY`); nada hardcodeado.
- **No truncar en silencio**: el digest avisa cuando recorta; los documentos ilegibles pese al OCR
  se listan en INFO FALTANTE.
- **Modelo LLM por env var**: `LOVEO_MODEL_ANALISIS` (default `claude-opus-5`), separado del
  `LOVEO_MODEL` barato que usa la Capa C para lectura masiva.

## Riesgos / decisiones abiertas

- **Costo por click**: cada análisis integral paga tokens de Opus. Si el volumen molesta, la salida
  es `LOVEO_MODEL_ANALISIS=claude-sonnet-5` — sin tocar código.
- **El censo de competencia no trae θ**: sale del historial de participaciones, no de un acta de
  visita con capacidades verificadas. Por eso la simulación NO lo usa (usaría θ=0 y concluiría que
  Loveo gana siempre). Para activarlo hace falta cargar `p_eett` por competidor.
- **La hoja Monte Carlo es estática**: se recalcula regenerando el informe, no editando el Excel.
