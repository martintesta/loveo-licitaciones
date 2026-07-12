# Loveo Licitaciones

Pipeline de licitaciones públicas de Chile (Mercado Público / ChileCompra) para **Loveo
Construcciones** (construcción modular en acero): **descubre** las licitaciones relevantes,
evalúa **admisibilidad**, **puntúa** el fit, **descarga y lee las bases** con IA, y presenta todo
en un tablero que además **aprende** de cada decisión. Local-first (H1: herramienta interna;
H2: semilla del SaaS).

El objetivo del producto en una frase: **ganar más y mejores licitaciones con menos esfuerzo
desperdiciado** — no perder una buena por no verla, decidir rápido si vale la pena ofertar, no
quedar inadmisible por un papel, no pasarse un deadline, y conocer el margen real.

---

## Metodología

Este proyecto se construye con dos metodologías encadenadas: una para decidir **qué** construir
(negocio → producto) y otra para decidir **cómo** construirlo (producto → desarrollo). El README
es parte del contrato: se mantiene actualizado a medida que el producto y el método evolucionan.

### 1) Negocio → Producto: ODI (Outcome-Driven Innovation)

ODI parte del **trabajo por resolver** (jobs-to-be-done): el cliente "contrata" el producto para
lograr un resultado, no por sus features. Se define el job, se listan sus **resultados deseados**
como enunciados medibles, y se prioriza por **importancia × insatisfacción**: donde el resultado
importa mucho y hoy está mal resuelto, ahí está la oportunidad. Las features salen de cerrar esas
brechas, no de una lista de deseos.

Aplicado a Loveo, el job es *"presentarme a las licitaciones que me convienen y ganar sin quemar
tiempo"*. Los resultados deseados subatendidos que ordenan el roadmap:

| Resultado deseado (ODI) | Brecha que ataca la herramienta |
|---|---|
| Minimizar las buenas licitaciones que se me pasan | Descubrimiento + **auditoría de recall** (ver qué descartó el filtro) |
| Minimizar el tiempo hasta decidir ofertar o no | **Score provisional** de triage (Priorizar / Revisar / Descartar) |
| Minimizar quedar inadmisible por un requisito | **Checklist de admisibilidad** extraído de las bases |
| Minimizar deadlines de cierre/visita perdidos | **Avisos de deadline** por email + tablero |
| Maximizar la confianza en el número que decide | **Confianza del score** visible (N/6 dimensiones) + **margen real** (en curso) |
| Minimizar depender de terceros para evaluar | Capa C (IA lee bases) + **cubicación asistida** (en diseño) |

Cada epic nace de uno de estos resultados; por eso las decisiones de producto se justifican contra
la brecha que cierran, no "porque estaría bueno".

### 2) Producto → Desarrollo: SDD (Spec-Driven Development)

SDD antepone una **especificación** a la implementación: en vez de pedirle código a un agente de
IA directo, primero se define qué hay que construir, con qué restricciones y con qué criterios de
verificación. La spec es el **contrato operativo entre el humano y el agente** — reduce la
ambigüedad, la carga de revisión y la deuda técnica de la generación asistida por IA.

Referencias: [ScrumManager — Spec-Driven Development](https://www.scrummanager.com/bok/index.php?title=Spec-Driven_Development_(SDD))
· [IBM — Spec-Driven Development](https://www.ibm.com/think/topics/spec-driven-development).

Las **cuatro fases** de SDD y cómo las instancia este repo:

1. **Requisitos** — el problema, los interesados, el comportamiento esperado y el alcance.
2. **Diseño** — decisiones técnicas, restricciones de arquitectura, criterios no funcionales.
3. **Tareas** — la implementación partida en pasos concretos, revisables y verificables.
4. **Implementación** — se genera el código siguiendo la spec; el humano revisa, testea e integra.

En la práctica, cada epic vive en `specs/<epic>/` con un `SPEC.md` (requisitos + diseño +
decisiones de producto) y un `PHASES.md` (tareas por fase con su criterio de "listo"). Trabajamos a
nivel **spec-anchored**: la spec se preserva y se actualiza a medida que la funcionalidad cambia (no
se descarta al terminar).

El "contrato" no depende de la buena voluntad: lo hace cumplir un **harness de calidad** que corre
en cada push y que es parte del método:

- `scripts/preflight.py` — escaneo de secretos + `ruff` + toda la suite de tests. Instalado como
  hook de pre-push (`.git/hooks/pre-push`).
- `scripts/review.py` — **revisión adversarial** del diff con un modelo (busca bugs e invariantes
  rotas). Los hallazgos válidos se aplican; los falsos positivos se rechazan con evidencia.
- `.github/workflows/ci.yml` — CI en GitHub que repite el preflight (con un Postgres real) para
  cazar los "anda en mi máquina".

La verificación humana sigue siendo esencial: la spec y el harness **reducen** —no eliminan— el no
determinismo de la IA.

---

## El embudo (8 pasos) — estado

```
1. DESCUBRIR    → API oficial ChileCompra (diaria)             ✅  discover.py
2. FILTRAR      → keywords límite de palabra + exclusiones      ✅  discover.py + recall.py (auditoría)
3. ADMISIBILIDAD→ regla dura (subcontratación) + checklist bases ✅  rules.py / Capa C
4. DESCARGAR    → adjuntos vía navegador headless (Capa B)       ◻  worker.py (corre local, IP CL)
5. PUNTUAR      → provisional (API) ✅ · Capa C (IA+bases) ✅ · margen real ◻  scoring.py / capac_score.py
6. PRESENTAR    → consola (login, ficha, listado, aprendizaje)   ✅  tablero3.py (Streamlit)
7. FEEDBACK     → aprobar/descartar + aprender de resultados     ✅  feedback.py / aprendizaje.py
8. ESTADO       → trazabilidad doble eje + eventos + avisos      ✅  db.py / notificar.py
```

Orquestación: `run_daily.py` (descubrir → admisibilidad → scoring provisional → avisos de deadline,
con bookkeeping en `runs`). El worker residencial (`worker.py`) hace la Capa B + C aparte.

## Las tres capas (dónde corre cada cosa)

| Capa | Qué hace | Dónde | Por qué |
|---|---|---|---|
| **A** | Descubrir + filtrar + score provisional | Cualquier lado (Render/cron) | `api.mercadopublico.cl` responde 200 a datacenter. |
| **B** | Descargar las bases (adjuntos) | **Local, IP chilena** | `www.mercadopublico.cl` bloquea datacenter (403/CAPTCHA). |
| **C** | Leer las bases con IA → score final | Donde corra el worker | Necesita las bases de la Capa B + `ANTHROPIC_API_KEY`. |

El **worker residencial** (`worker.py`) encadena B → C en una pasada: baja las bases y las analiza,
así el score pasa de 4/6 a 5/6 dimensiones solo. Como depende de un scraping frágil (WAF+CAPTCHA),
registra un **heartbeat** y avisa (banner + email) si se queda mudo, para que el score no se degrade
en silencio. Ver `WORKER.md` y `scripts/worker_doctor.py`.

## Honestidad del score (provisional vs final)

`scoring.py` calcula lo derivable de la API — **logístico** (distancia a la base más cercana, ×3 si
>300 km), **alineación**, **repetibilidad** y **cash flow** parcial. **Margen** y **complejidad**
quedan *pendientes de bases/cubicación*. Por eso es un **score provisional para triage**
(Priorizar ≥85 / Revisar ≥60 / Descartar), **no** un GO/NO-GO. La Capa C evalúa la complejidad y el
techo de presupuesto; el **margen real** sigue pendiente de la cubicación (ver roadmap #4). La UI
muestra la **confianza** (cuántas de las 6 dimensiones tienen dato real) para que el número se lea
según lo que sostiene.

Dual-base: el logístico se evalúa contra la base más cercana (Pirque + Puerto Montt). Distancias en
`scoring.py:BASES` son aproximadas — CALIBRAR.

## Aprendizaje e inteligencia propia

- **Descartes y resultados** (`aprendizaje.py`): al descartar o marcar ganada/perdida con un motivo,
  el sistema ajusta (display-only, reversible) el score de licitaciones parecidas — victorias suben,
  pérdidas por mal fit bajan, pérdidas por competencia/precio no tocan el score.
- **Auditoría de recall** (`recall.py`): registra lo que el filtro descartó (candidatas de la red
  amplia + sobre-exclusiones) para cazar falsos negativos.
- **Reputación de pago del comprador** (`comprador.py`): señal de la Ficha Comprador cargada a mano
  (está tras CAPTCHA), aplica a todas las licitaciones del organismo.

## Estado / máquina de estados (doble eje)

```
estado_revision : nueva → en_revision → (descartada | aprobada)
estado_resultado: (si aprobada) pendiente → presentada → (ganada | perdida | desierta)
```

## Cómo correr

```bash
pip install -r requirements.txt
python -m playwright install chromium          # navegador para la Capa B

python db.py                                    # crea loveo.db + ./storage (o usa DATABASE_URL=Neon)
python run_daily.py 11062026                    # descubrir + admisibilidad + scoring (+ avisos)
python run_daily.py --backfill 5                # últimos 5 días hábiles no procesados

# Capa B + C — CORRER LOCAL (IP chilena):
python scripts/worker_doctor.py                 # valida DATABASE_URL/ticket/API key/Playwright/cola
python calibrate_ficha.py 2263-53-LE26          # 1 vez: calibrar navegación a la ficha
python worker.py                                # loop: baja bases (B) + analiza (C)

streamlit run tablero3.py                       # consola: login, listado, ficha, aprendizaje
```

Config: el ticket va en `.env` (`LOVEO_CHILECOMPRA_TICKET`), nunca en `config_local.py`.
`config_local.py` (gitignored) tiene las keywords/umbrales; `config_local_example.py` es la
plantilla pública. Avisos por email: ver `NOTIFICACIONES.md`.

## Módulos

| Módulo | Rol |
|---|---|
| `discover.py` | Capa A: API, filtro (con exclusiones aprendidas), detalle. |
| `recall.py` | Auditoría de recall: qué descartó el filtro y por qué. |
| `rules.py` | Admisibilidad (regla dura). No rechaza por boilerplate de Prohibición. |
| `scoring.py` | Score Atlas provisional + mapa región→distancia dual-base. |
| `worker.py` | Worker residencial: Capa B (descarga) + Capa C (análisis) + heartbeat. |
| `download.py` | Capa B: adjuntos vía Playwright (corre local). |
| `bases.py` / `capa_c.py` | PDF→texto (pdfplumber + OCR) y extracción estructurada con IA. |
| `capac_score.py` | Aplica la Capa C al score (complejidad + techo de presupuesto). |
| `cubicacion.py` | Cubicación e ingreso de precios de referencia (hoy desde Excel). |
| `feedback.py` / `aprendizaje.py` | Descartes/resultados con motivo → ajuste asistido del score. |
| `comprador.py` | Reputación de pago por comprador (señal Ficha Comprador manual). |
| `notificar.py` | Avisos de deadline (cierre/visita) + worker mudo, por email. |
| `extract.py` / `competencia.py` / `relicitaciones.py` | Inteligencia competitiva, desiertas, re-licitación. |
| `tablero_data.py` / `tablero3.py` | Lectura única para la UI + consola bidireccional (Streamlit). |
| `textnorm.py` | Normalización de texto compartida (una sola fuente para keywords/regiones). |
| `db.py` / `schema_v3.py` | Backend SQLite↔Postgres + esquema. `schema_v2.py` es legacy. |
| `scripts/preflight.py` · `scripts/review.py` · `scripts/worker_doctor.py` | Harness de calidad + doctor del worker. |

## Roadmap (por resultado ODI subatendido)

1. **Robustez del worker** ✅ — heartbeat + alerta de silencio (banner + email).
2. **Avisos de deadline** ✅ — email digest, deduplicado, enganchado a `run_daily`.
3. **Admisibilidad como checklist** ✅ — requisitos/garantías de las bases visibles en la ficha.
4. **Cubicación asistida → margen real** ◻ — la IA arma el listado de materiales desde las bases,
   precia con referencia clickeable (ecommerce), y aprende "recetas" por tipo de producto para dejar
   de depender de la cubicación de un tercero. Cierra el margen del score. (En diseño; `specs/`.)
5. **Endurecer operación** ◻ — Sentry, backups de Neon, roles, warm-up de Render.

## Docs relacionados

`WORKER.md` (Capa B+C, doctor, scheduler) · `NOTIFICACIONES.md` (avisos por email) ·
`CALIBRACION_CAPA_B.md` · `DEPLOY.md` · `RUNBOOK.md` · `PLAN_DATOS.md` · `specs/` (specs por epic).
