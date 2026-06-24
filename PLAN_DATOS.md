# Plan de datos — loveo-licitaciones

Cómo el tablero pasa de mockup a **data real**. Capa de datos local-first sobre SQLite.
Invariante: *ningún código de Mercado Público se muestra sin su registro real detrás*.

## Modelo de datos (tablas nuevas, migración `schema_v2.py`)

| Tabla | Qué guarda | Fuente |
|---|---|---|
| `adjudicaciones` | cabecera del bloque Adjudicación: fecha, N° oferentes, URL acta | **API** (detalle) — verificado |
| `items` | líneas (producto, cantidad, unidad) + ganador por línea (RUT, nombre, $ unitario) | **API** (Items[].Adjudicacion) — verificado |
| `competidores` | registro por RUT: razón social, contacto, desde qué año | **Derivado** de items; `contacto` = manual/lookup (NULL) |
| `participaciones` | RUT × licitación × resultado × monto × año | **Derivado**; `ganada` real, `perdida` = futuro |
| `relicitaciones` | enlace desierta original → re-licitación + score de match | **Derivado** (heurístico) |

## Orden de build (cada paso es código que corre y se probó)

1. **`schema_v2.py`** — crea las 5 tablas (idempotente). *Aplicado.*
2. **`extract.py`** — parsea `json_detalle` → adjudicaciones + items + competidores + participaciones(ganada).
   *Verificado contra 2263-53: PABYMAC, vigas, $13.000.000/u, $26.000.000 total, 1 oferente, 2026.*
3. **`competencia.py`** — `resumen()`, `ficha(rut)`, `facturado_por_anio(rut)`.
   *Verificado: PABYMAC → 1 participación, 1 ganada, $26M; facturado {2026: $26M}.*
4. **`relicitaciones.py`** — `detectar()`: misma entidad + nombre Jaccard ≥ 0,45 + fecha posterior.
   *Núcleo verificado: par real = 1,00; no relacionada = 0,00.*
5. **Cableado en `run_daily.py`** — tras el upsert llama `extract.extraer`; al cierre, `relicitaciones.detectar`.
   *Verificado end-to-end sobre el día cacheado (0 errores).*

## Fuentes: qué es API, qué es derivado, qué falta

- **API (verificado, sin scraping):** adjudicación, ganador, precio unitario, N° oferentes, items.
- **Derivado (cálculo local):** competidores, ganadas, facturado (proxy = monto adjudicado), enlaces de re-licitación.
- **Futuro (segundo endpoint):**
  - *Perdidas* de un competidor → ofertas públicas tras apertura técnica.
  - *Facturado exacto* → Órdenes de Compra por RUT (hoy se usa el monto adjudicado como proxy).
  - *Contacto del competidor* → ficha de proveedor o carga manual.
- **Requiere ticket propio + IP residencial CL:** la descarga de bases/anexos (Capa B) para el Asistente IA Nivel 3.

## Lo que esto desbloquea en el tablero

- **Inteligencia competitiva** → tabla `adjudicaciones` + `items` (dato real, ya probado).
- **Seguimiento de Competencia** → `competencia.resumen()` / `ficha()` / `facturado_por_anio()`.
- **Desiertas + re-licitación** → `estado_mp=7` + tabla `relicitaciones`.
