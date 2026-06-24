# Rediseño del tablero Loveo Construcciones — Spec v2

> **Objetivo de la herramienta:** cada semana, decidir rápido a qué licitaciones fit conviene
> presentarse, **sin perder un cierre**, descartando falsos positivos en segundos, y con la munición
> para ganarla (bases, quién compite, a qué precio). El score es **triage provisional**; el GO/NO-GO
> final necesita Capa C + la **cubicación de Valentina**. Es herramienta de **decisión**, no un visor.
> Local-first (un solo `loveo.db`), nada inventado. Interno (H1) + semilla SaaS (H2).
>
> Estética: chasis **consola** del mockup *Elum Insight* (rail oscuro), en **Streamlit** (backend que
> consulta `loveo.db`). Estado de cada dato: ✅ hay hoy · 🔧 hay que construir · ❓ decisión abierta.

---

## 0. Principios de diseño (del review crítico)

1. **Acción sobre proceso** — el Inicio responde "¿qué hago hoy?", no "¿cómo está el embudo?".
2. **Triage veloz** — descartar un FP y aprender la exclusión es el loop diario #1: un clic.
3. **Inteligencia en la decisión** — la competencia/desiertas se inyectan en la ficha, no viven solo en pestañas.
4. **Camino al GO/NO-GO explícito** — la UI muestra qué falta para decidir cada licitación (bases→Capa C→cubicación).
5. **Honestidad del score + score evolutivo** — liderar con el triage (Priorizar/Revisar/Descartar); el número, secundario y siempre "prov.". El score **se recalibra con el input humano**: aprobar/descartar/corregir y aprender exclusiones realimentan el scoring (no es un número estático). **Cada aprobación/descarte guarda una nota del porqué** (queda en la trazabilidad y alimenta el aprendizaje).
6. **Fidelidad híbrida** — alta fidelidad donde se *mira/muestra*; Streamlit nativo y veloz donde se *actúa*.

---

## 1. Lenguaje visual

- Rail oscuro (`#0E1115`), nav por íconos agrupada, badges de conteo.
- Marca: **Loveo** + subtítulo **Construcciones** (mono).
- **Teal `#0E7490`** = marca (logo, KPIs, barra activa). **Ámbar `#F59E0B`** = señal/acción ("nuevo / requiere acción").
- Triage semántico: verde `#047857` Priorizar/Ganada · ámbar `#F59E0B` Revisar · rojo `#B91C1C` Descartar/Perdida.
- Tipografía: Montserrat (títulos) · Inter (cuerpo) · JetBrains Mono (códigos, números, labels). Radio 3px, tablas densas.

---

## 2. Elementos globales

| Elemento | Qué hace | Datos |
|---|---|---|
| Buscador global (topbar) | código, nombre, organismo, comuna/región | ✅ |
| Filtro por keywords | acota por términos de negocio | ✅ `config_local.py` |
| Contador en vivo | "N señales · 7d" | ✅ `eventos` |
| Ficha de detalle | click → ficha con decisión + intel (ver §4) | ✅/🔧 |

---

## 3. Navegación

```
OPERACIÓN
  🏠 Inicio       — qué hacer hoy
  ⚡ Señales      — bandeja de triage (badge: nuevas 7d)
  📑 Listado      — universo completo, filtro por ID + keyword
  🎯 Radar        — tu seguimiento (toggle tabla / kanban) — incluye lo que era "Mi pipeline"
  🗺️ Mapa         — ubicación geográfica + tier logístico
INTELIGENCIA
  📊 Inteligencia competitiva
  🏜️ Desiertas
  🔭 Seguimiento de Competencia
ASISTENTE
  🤖 Asistente IA
(futuro) 💾 Mis vistas
```
> Cambio v2: **Radar y "Mi pipeline" son UNA sola vista** (eran el mismo set: lo que seguís). Radar tiene
> toggle **tabla ↔ kanban** en vez de dos pestañas separadas.

### 🏠 Inicio — "qué hacer hoy" (acción, no proceso)
Orden de la pantalla, de arriba a abajo:
1. **Buscador + filtro por keywords**.
2. **⏰ Cierran esta semana** — vigentes con `fecha_cierre` próxima, ordenadas por urgencia × score. *Perder un cierre = oportunidad perdida; esto va primero.* ✅ (`fecha_cierre`, `DIAS_ALERTA_CIERRE`)
3. **📥 Nuevas fit sin revisar** — bandeja rápida (link a Señales). ✅
4. **KPIs** (chicos): Fit este año · Nuevas 7d · En seguimiento · Cierran ≤5d. ✅
5. **Clasificación anual** — por **mes** y por **categoría/keyword**, con tabla ID + link MP. ✅ + 🔧 link
6. **Embudo por estado** — métrica de contexto, abajo y compacto. ✅

### ⚡ Señales — bandeja de triage
Feed de gatillos (7d): **nuevas descubiertas + cambios relevantes** (re-licitada, cierra pronto, adjudicada). Fuente `eventos`. ✅
- **Acciones inline de un clic**: ✓ Seguir · 🗑 Descartar **+ aprender término** · → abrir ficha. 🔧 (acción rápida)
- Meta: despachar 10 candidatas nuevas en ~30s. Es la pantalla más usada.
- → por ser action-heavy, va en **Streamlit nativo** (no HTML read-only).

### 📑 Listado — universo completo, buscable
Tabla maestra de **todas** las licitaciones.
- **Filtro por ID/código MP** (exacto o parcial) **y por palabra clave** (nombre/organismo). ✅
- Columnas: código · nombre · región · monto · cierre · **triage + score(prov.)** · estado · admisible · link MP.
- **Marcar resultado desde acá** 🔧: una licitación se puede marcar **Ganada** (o perdida/desierta) directo desde el listado, sin pasar por todo el flujo. (`db.set_estado_resultado`)
- Diferencia con Radar: Listado = universo de referencia; Radar = tu set de trabajo.
- 🔧 Paginación / filtro server-side (crece con los meses).

### 🎯 Radar — tu seguimiento (tabla ↔ kanban)
Lo que seguís activamente. Toggle:
- **Tabla densa**: score+triage, región, cierre, **docs**, link MP.
- **Kanban**: por máquina de estados (Nuevas · En revisión · Aprobadas · Presentadas · Cerradas), avance por botón "Mover a…". 🔧 (kanban interactivo)
- **Alta manual por código MP** 🔧: pegás un código que el sistema no descubrió → `discover.traer_detalle` → upsert → `seguir=1`. Cubre el hueco del descubrimiento automático.
- Filtros (chips): admisibles · vigentes · región · triage.
- "Seguir" = columna nueva `seguir` (sigue sin importar el estado de revisión).

### 🗺️ Mapa — ubicar las licitaciones
Vista geográfica del pipeline: cada licitación posicionada por región/comuna.
- Coloreado por **tier logístico** desde las bases (Puerto Montt / Pirque) — la distancia es dimensión real del score (×3 si >300 km). 🔧
- Filtro compartido con Radar/Listado (región, triage, vigentes).
- Ayuda a decidir de un vistazo qué está "cerca y conviene" vs. lejos. Datos: `region`/`comuna` ✅; georreferencia 🔧.

### Grupo INTELIGENCIA (análisis profundo; la señal clave se inyecta en la ficha, §4)
- **📊 Inteligencia competitiva** — adjudicaciones: quién gana, precio, oferentes. ✅
- **🏜️ Desiertas** — estado_mp=7 + re-licitación enlazada. ✅
- **🔭 Seguimiento de Competencia** — competidores: participaciones, ganadas/perdidas, facturado/año. ✅

### 🤖 Asistente IA
Text-to-SQL sobre la base. 🔧 cablear `ANTHROPIC_API_KEY` (ya en el entorno).

---

## 4. Ficha de detalle — la pantalla de decisión
- Cabecera: código + nombre + badges (admisible / estado / posible FP).
- Meta: región, organismo, monto, cierre, visita, estado MP.
- **Camino al GO/NO-GO** (checklist explícito): 🔧
  `Bases descargadas` ✅/⏳ → `Capa C leída` → `Cubicación de Valentina cargada` → **Margen final + GO/NO-GO**.
  Mientras falte la cubicación, el margen queda "pendiente" (invariante).
- **Score · 6 dimensiones** con barras; margen y complejidad marcados "pendiente bases". ✅
- **Inteligencia inyectada** 🔧: "competencia histórica en esta región/organismo", "desiertas relacionadas",
  "este organismo dejó N desiertas / 1 oferente" — la munición, en el lugar donde decidís.
- **Documentos** 🔧: tres orígenes →
  (a) descargados por Capa B ✅, (b) **adjunto manual** (subir PDF/archivo), (c) **link de Google Drive** (pegás la URL; queda asociada a la licitación). Cada doc guarda su fuente.
- **💬 Chat con Claude sobre la documentación** (Capa C, scope = esta licitación) 🔧:
  - Preguntás sobre las bases; la fuente puede ser un **doc adjunto** o un **link de Drive** (o lo ya descargado).
  - **Persiste la info relevante**: la extracción estructurada (presupuesto, plazos, garantías, criterios+pesos, requisitos, complejidad) y las respuestas clave quedan **guardadas en la ficha** → no hay que volver a abrir los PDFs ni el Drive.
  - Alimenta el **camino al GO/NO-GO** (presupuesto/complejidad de Capa C) de arriba.
- **Trazabilidad**: timeline de `eventos` (incluye las **notas** de aprobación/descarte). ✅
- Acciones: Aprobar · Descartar — **ambas piden una nota del porqué** 🔧 · aprender término · **Corregir score** (ajuste humano que recalibra) · Marcar resultado (ganada/perdida/desierta) · Abrir en MP · Mover a…  ✅ (`feedback.py`).

---

## 5. Faltantes técnicos (consolidado)
- 🔧 Link a ficha MP desde `CodigoExterno` (sacar formato de `download.py`/`calibrate_ficha.py`).
- 🔧 Columna `seguir` en `licitaciones` (+ helper `db.py`).
- 🔧 Alta manual por código (form → `traer_detalle` → upsert → `seguir=1`).
- 🔧 Acciones inline rápidas en Señales (seguir / descartar+aprender).
- 🔧 Checklist GO/NO-GO + **input de cubicación de Valentina** (costo real → margen final).
- 🔧 Inyección de intel competitiva en la ficha (queries `competencia.*` por región/organismo).
- 🔧 Kanban interactivo (botón "Mover a…") + toggle tabla/kanban en Radar.
- 🔧 **Ingestión de docs** (3 vías): Capa B ✅ · adjunto manual (PDF → `storage/<codigo>/`) · **link de Google Drive** (URL asociada). → `documentos` necesita `fuente` (capa_b/adjunto/drive) y `url` (ruta_local opcional para links).
- 🔧 **Analizar bases con IA + actualizar score** (Capa C, `capa_c.py`) — el lever central:
  - Botón en la ficha "Analizar bases" → lee el doc (link Drive **archivo compartido** o PDF), extrae presupuesto/plazos/garantías/requisitos/complejidad y **actualiza margen/complejidad a "estimado (bases)"** (NO final — el margen real lo da la cubicación de Valentina).
  - **Cachea + muestra "Analizado el [fecha] · modelo · ~N tokens"**; no re-corre solo. Re-analizar = explícito (gasta tokens); marcar si el doc cambió desde el último análisis.
  - Estimación de costo antes de gastar (`--dry`); modelo barato (Haiku) por defecto, solo texto.
  - El cambio de score queda en trazabilidad (score evolutivo). Persiste en **tabla `analisis_bases`** (codigo, json_extraccion, resumen, ts, modelo, tokens).
- 🔧 **Chat con Claude por licitación** (Q&A sobre las bases ya analizadas) — usa el texto/extracción cacheada para no re-leer.
- 🔧 **Notas del porqué** en aprobar/descartar (rationale obligatorio) → `feedback_humano` + evento tipo `nota`.
- 🔧 **Marcar resultado desde el Listado** (ganada/perdida/desierta) (`db.set_estado_resultado`).
- 🔧 Paginación en Listado.
- 🔧 **Score evolutivo**: el feedback humano (aprobar/descartar/corregir/exclusiones **+ las notas**) recalibra el scoring (`feedback.py` + `scoring.py`).
- 🔧 **Mapa**: georreferencia por región/comuna + coloreado por tier logístico (Puerto Montt/Pirque).
- 🔧 **Cash flow ajustado por reputación de pago del comprador** (pedido): ponderar el plazo nominal (Modalidad)
  contra el **comportamiento de pago real** del organismo. Cash flow base ✅ usa Modalidad + `CASHFLOW_TIER`.
  - Dato fuente: **Ficha Comprador** de ChileCompra (datos-abiertos) → **días promedio de pago**, reclamos por pago, volumen adjudicado. Cruce por **`CodigoOrganismo`** (ya lo guardamos en el detalle).
  - **Blocker (investigado)**: la Ficha Comprador está tras un WAF → **403 incluso desde IP residencial** vía `requests`. **El bulk NO sirve**: datos.gob.cl no tiene datasets de ChileCompra; `datos-abiertos.chilecompra.cl/descargas` = 403; el portal viejo `datosabiertos.chilecompra.cl` ya no resuelve. La métrica "días de pago" es **calculada y solo vive en la Ficha Comprador** (SPA WAF). → Único camino viable: **Playwright/navegador headless** (como Capa B / skill `/browse`) que renderiza el JS y pasa el challenge, cacheando en tabla `compradores`. Subsistema propio.
  - `CantidadReclamos` del detalle es reclamos GENERALES del organismo y **solo sirve normalizado por volumen** → no usar crudo.
  - Fórmula propuesta: cash flow = base(Modalidad) ajustado por `días_promedio_pago` vs plazo nominal + reclamos/volumen.
- ❓ "Mis vistas" (filtros guardados) — post-MVP / SaaS.

---

## 6. Fidelidad por pantalla (split pragmático)
| Pantalla | Enfoque |
|---|---|
| Inicio, Inteligencia, Ficha (vista) | **Alta fidelidad** (HTML embebido) — mirar y mostrar |
| Señales (triage), Radar (acciones), feedback | **Streamlit nativo** — rápido para actuar |

## 7. Orden de construcción sugerido
1. Chasis (rail + topbar + buscador) + **Inicio** con datos reales.
2. **Señales** como bandeja de triage (acciones inline).
3. **Listado** (filtro ID + keyword) y **Radar** (tabla/kanban + alta manual).
4. **Ficha** con camino al GO/NO-GO + intel inyectada + corregir score.
5. **Mapa** (georreferencia + tier logístico) e Inteligencia con el look nuevo.
6. Pulido visual de las pantallas de "mostrar" + Asistente IA.
7. **Margen / cubicación** (§8) — subsistema propio, depende de Capa C.

---

## 8. Margen, cubicación y trazabilidad de costos

El **Margen** (dimensión ×3, hoy neutro/placeholder) se construye en **dos capas** que se refuerzan:

### A. Cubicación tipo (automática)
1. **Capa C lee las especificaciones técnicas** de las bases → identifica el producto y sus parámetros
   (tipo, dimensiones, m², materiales, cantidades, terminaciones).
2. El sistema **estima el valor** del producto con dos fuentes:
   - **Precios reales de otras licitaciones** — ✅ ya están en `adjudicaciones` + `items`
     (ganador, precio unitario, monto, región). Base de precios interna y gratis para bootstrap.
   - **Búsqueda en internet** de precios de materiales/productos comparables (cuando falte referencia interna).
3. Resultado: una **cubicación tipo** → techo de presupuesto vs. costo estimado → **margen estimado**
   que alimenta la dimensión Margen (deja de ser neutro; queda marcado "estimado", no aún "real").

### B. Cubicación de Valentina (Excel ingestado)
- **Refuerza y corrige** los precios de los elementos individuales con datos reales de la operación.
- Se **ingesta un Excel** con el itemizado: **materiales · mano de obra · transporte · otros**.
- Se guarda con **trazabilidad**: cada ítem con precio, unidad, cantidad, fuente y fecha → mejora el
  **scoring futuro** y permite ver la **evolución de costos en el tiempo**.
- Flujo: cubicación tipo (auto, aproximada) → Valentina la mejora (real) → el Margen pasa de *estimado* a *acertado*
  y el GO/NO-GO se vuelve confiable.

### Estructura real del Excel (muestra Talagante, formato variable)
Una hoja. Arriba: `Ingreso con IVA`, `Ingreso sin IVA`. Itemizado por filas:
`B = partida/sección` (Estructura Acero, Tabiquería, Sala RX, Cubierta, MANO DE OBRA, TRASLADO, FLETES, SILLON…),
`C = ítem`, `D = cantidad`, `E = unidad`, `F = precio unitario`, `G = total`, `H = devengado`,
`I = estado de pago`, `J–N = pagos por fecha`. Abajo: `Costo Total`, `Falta gastar`, `Presupuesto Devengado`.
→ Margen real = Ingreso sin IVA − Costo Total (Talagante: 80.000.000 − 44.450.320 ≈ 35,5M / 44%).
**El formato puede variar** → el parser debe **detectar** (no hardcodear columnas): localizar fila de ingresos,
tratar filas con B como cabecera de partida y filas con C como ítems.

### Modelo de datos nuevo (derivado del archivo real)
- `cubicaciones` — cabecera por proyecto/licitación: `ingreso_con_iva`, `ingreso_sin_iva`, `costo_total`,
  `margen` (= ingreso_sin_iva − costo_total), `margen_pct`, `origen` (`valentina`/`tipo`), `archivo`, `fecha`, `version`.
- `cubicacion_items` — itemizado: `partida` (B, verbatim), `grupo` (derivado: `material`/`mano_obra`/`transporte`/`otros`),
  `descripcion`, `cantidad`, `unidad`, `precio_unitario`, `total`, `devengado`, `estado_pago`.
- `precios_referencia` — catálogo destilado de los ítems: `descripcion`, `unidad`, `precio_unitario`,
  `fuente` (`valentina`/`adjudicacion`/`web`), `proyecto`, `region`, `fecha`. Alimenta la cubicación tipo y la trazabilidad.
- Clasificación `grupo`: por nombre de partida (MANO DE OBRA→mano_obra; TRASLADO/FLETES→transporte; SILLON/Otros→otros; resto→material).
- Bonus: las columnas de pago (devengado / pagos por fecha) sirven también para afinar la dimensión **cash flow**.

### Faltantes / decisiones
- 🔧 Capa C: extracción de especificaciones técnicas (base en `bases.py`/`capa_c.py`).
- 🔧 Motor "cubicación tipo": specs → precios (interno `items` + web) → margen estimado.
- 🔧 Ingestión del **Excel de Valentina** → `cubicaciones` + `cubicacion_items` + `precios_referencia`.
- 🔧 Vista de **trazabilidad de costos** (evolución de precios por material/ítem en el tiempo).
- ❓ **Estructura del Excel de Valentina** (columnas/itemizado) — definir con una muestra real.
- ❓ Fuente de búsqueda web de precios (sitios/connector) y unidad de cubicación (m² / unidad / proyecto).
- Secuencia: depende de Capa C; subsistema propio, posterior al CRUD del tablero.
