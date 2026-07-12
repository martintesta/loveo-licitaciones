# Plataforma de Inteligencia de Licitaciones

Descubre, evalúa y prioriza licitaciones públicas de forma automática, lee sus bases con IA, y
**aprende de cada decisión** para afinar el criterio con el tiempo. Pensada para **Latinoamérica**,
con adaptadores por mercado — hoy operativa en un primer mercado, con más países en el roadmap.

El objetivo en una frase: **ganar más y mejores licitaciones con menos esfuerzo desperdiciado** — no
perder una buena por no verla, decidir rápido si conviene ofertar, no quedar afuera por un requisito,
no pasarse un plazo, y conocer el margen antes de decidir.

Local-first: opera contra fuentes públicas y una base propia. El conocimiento que genera (criterio,
histórico, estimaciones) queda del lado del usuario y **compone** proyecto a proyecto.

---

## Metodología

El proyecto se construye con dos metodologías encadenadas: una para decidir **qué** construir
(negocio → producto) y otra para decidir **cómo** construirlo (producto → desarrollo). El README es
parte del contrato: se mantiene actualizado a medida que el producto y el método evolucionan.

### 1) Negocio → Producto: ODI (Outcome-Driven Innovation)

ODI parte del **trabajo por resolver** (jobs-to-be-done): el cliente "contrata" el producto para
lograr un resultado, no por sus features. Se define el job, se listan sus **resultados deseados**
como enunciados medibles, y se prioriza por **importancia × insatisfacción**: donde el resultado
importa mucho y hoy está mal resuelto, ahí está la oportunidad. Las features salen de cerrar esas
brechas, no de una lista de deseos.

El job central: *"presentarme a las licitaciones que me convienen y ganar sin quemar tiempo"*. Los
resultados que ordenan el roadmap, y cómo los aborda la plataforma:

| Resultado deseado | Cómo lo aborda la plataforma |
|---|---|
| No perder buenas oportunidades | Descubrimiento amplio + auditoría de cobertura |
| Decidir rápido si ofertar o no | Score de triage con **confianza explícita** |
| No quedar inadmisible por un requisito | Requisitos clave extraídos de las bases |
| No perder plazos (cierre / visita) | Avisos automáticos |
| Confiar en el número que decide | Evaluación multidimensional + margen estimado |
| No depender de terceros para evaluar | Lectura de bases con IA + estimación asistida que **aprende** |

Cada epic nace de uno de estos resultados; las decisiones de producto se justifican contra la brecha
que cierran.

### 2) Producto → Desarrollo: SDD (Spec-Driven Development)

SDD antepone una **especificación** a la implementación: en vez de pedirle código a un agente de IA
directo, primero se define qué construir, con qué restricciones y con qué criterios de verificación.
La spec es el **contrato operativo entre el humano y el agente** — reduce la ambigüedad, la carga de
revisión y la deuda técnica de la generación asistida por IA.

Referencias: [ScrumManager — Spec-Driven Development](https://www.scrummanager.com/bok/index.php?title=Spec-Driven_Development_(SDD))
· [IBM — Spec-Driven Development](https://www.ibm.com/think/topics/spec-driven-development).

Las **cuatro fases** de SDD y cómo las instancia este repo:

1. **Requisitos** — el problema, los interesados, el comportamiento esperado y el alcance.
2. **Diseño** — decisiones técnicas, restricciones de arquitectura, criterios no funcionales.
3. **Tareas** — la implementación partida en pasos concretos, revisables y verificables.
4. **Implementación** — se genera el código siguiendo la spec; el humano revisa, testea e integra.

En la práctica, cada epic vive en `specs/<epic>/` con un `SPEC.md` (requisitos + diseño + decisiones)
y un `PHASES.md` (tareas por fase con su criterio de "listo"). Trabajamos a nivel **spec-anchored**:
la spec se preserva y se actualiza a medida que la funcionalidad cambia.

El "contrato" no depende de la buena voluntad: lo hace cumplir un **harness de calidad** que corre en
cada push y que es parte del método:

- `scripts/preflight.py` — escaneo de secretos + `ruff` + toda la suite de tests (hook de pre-push).
- `scripts/review.py` — **revisión adversarial** del diff con un modelo (busca bugs e invariantes
  rotas); los hallazgos válidos se aplican, los falsos positivos se rechazan con evidencia.
- `.github/workflows/ci.yml` — CI que repite el preflight (con base real) para cazar los "anda en mi
  máquina".

La verificación humana sigue siendo esencial: la spec y el harness **reducen** —no eliminan— el no
determinismo de la IA.

---

## El embudo (de la fuente pública a la decisión)

```
1. DESCUBRIR    → fuentes oficiales del mercado (diario)
2. FILTRAR      → relevancia por criterios + auditoría de cobertura
3. ADMISIBILIDAD→ reglas duras + requisitos leídos de las bases
4. OBTENER DOCS → bases/adjuntos de la ficha
5. PUNTUAR      → score de triage (datos públicos) → score afinado (IA + bases) → margen
6. PRESENTAR    → consola: login, ficha, listado, aprendizaje
7. FEEDBACK     → aprobar/descartar + aprender de los resultados
8. ESTADO       → trazabilidad + avisos de plazo
```

Un orquestador diario corre el descubrimiento → admisibilidad → scoring → avisos, con bookkeeping.
La obtención de documentos + la lectura con IA corren en un worker aparte.

## Arquitectura por capas (portable entre mercados)

| Capa | Qué hace | Dónde corre |
|---|---|---|
| **A** | Descubrir + filtrar + score de triage | Donde sea (la API pública responde a datacenter). |
| **B** | Obtener las bases/adjuntos | Según el mercado, algunas fuentes bloquean el acceso automatizado de datacenter → un componente corre en **red local** de ese país. |
| **C** | Leer las bases con IA → score afinado | Donde corra el worker (necesita las bases de la Capa B). |

Cada mercado se integra como un **adaptador** (fuente de datos + reglas de admisibilidad + parámetros
locales). El núcleo — scoring, aprendizaje, cubicación asistida, UI — es común. La Capa B puede
requerir un punto de presencia local según cómo publique cada país sus bases.

## Honestidad del score

La plataforma **no inventa**: separa lo que puede derivar de datos públicos de lo que requiere leer
las bases (o una cubicación). El número se presenta con su **nivel de confianza** — cuántas de las
dimensiones tienen dato real vs. las que quedan en un neutro hasta tener más información. Por eso el
score es primero para **triage** (priorizar / revisar / descartar) y se vuelve un GO/NO-GO recién
cuando hay bases y costos.

## Aprendizaje e inteligencia propia

La plataforma mejora con el uso, y ese conocimiento queda del lado del usuario:

- **Aprende de las decisiones** (descartes y resultados con su motivo) para ajustar el criterio de
  licitaciones parecidas — de forma explícita y reversible.
- **Audita su propia cobertura**: registra lo que el filtro descartó para cazar falsos negativos.
- **Estimación asistida que compone**: a partir de las bases arma un borrador que el usuario cura, y
  cada curación afina las próximas — la curación se achica proyecto a proyecto.

## Cómo correr

```bash
pip install -r requirements.txt
python -m playwright install chromium          # navegador para la Capa B

python db.py                                    # crea la base local (o usa DATABASE_URL)
python run_daily.py <fecha>                     # descubrir + admisibilidad + scoring (+ avisos)
python run_daily.py --backfill 5                # últimos 5 días hábiles no procesados

# Capa B + C — corre en el punto de presencia local del mercado:
python scripts/worker_doctor.py                 # valida credenciales / navegador / cola
python worker.py                                # loop: obtiene bases (B) + analiza (C)

streamlit run tablero3.py                       # consola: login, listado, ficha, aprendizaje
```

Config por entorno: las credenciales del mercado y de la IA van en `.env` (nunca en el código).
`config_local.py` (gitignored) tiene los parámetros/criterios locales; `config_local_example.py` es
la plantilla pública. Avisos por email: ver `NOTIFICACIONES.md`.

## Módulos (por capacidad)

| Capacidad | Módulos |
|---|---|
| Descubrir + filtrar + cobertura | `discover.py`, `recall.py`, `filters.py` |
| Admisibilidad + reglas | `rules.py` |
| Score y su honestidad | `scoring.py`, `capac_score.py` |
| Obtener + leer bases (IA) | `worker.py`, `download.py`, `bases.py`, `capa_c.py` |
| Cubicación asistida | `cubicacion_ia.py`, `cubicacion.py` |
| Aprendizaje | `feedback.py`, `aprendizaje.py`, `comprador.py` |
| Avisos de plazo | `notificar.py` |
| Inteligencia de mercado | `extract.py`, `competencia.py`, `relicitaciones.py` |
| UI / consola | `tablero_data.py`, `tablero3.py`, `components/console/` |
| Base + utilidades | `db.py`, `schema_v3.py`, `textnorm.py` |
| Harness de calidad | `scripts/preflight.py`, `scripts/review.py`, `scripts/worker_doctor.py` |

## Roadmap (por resultado ODI)

1. **Robustez de la obtención de datos** ✅ — monitoreo + alerta si el pipeline se queda mudo.
2. **Avisos de plazo** ✅ — email automático, deduplicado.
3. **Admisibilidad como checklist** ✅ — requisitos de las bases visibles antes de ofertar.
4. **Cubicación asistida → margen** ◧ — estimación de costos desde las bases que el usuario cura y
   que la plataforma aprende, para cerrar el margen del score sin depender de un tercero. Spec en
   `specs/cubicacion-asistida/` (borrador, curación, precios con referencia clickeable y margen al
   score — hechos; sigue el aprendizaje de recetas por tipo de producto).
5. **Más mercados de Latinoamérica** ◻ — nuevos adaptadores (fuente + reglas + parámetros) sobre el
   mismo núcleo.
6. **Endurecer operación** ◻ — observabilidad, backups, roles.

## Docs relacionados

`WORKER.md` · `NOTIFICACIONES.md` · `DEPLOY.md` · `RUNBOOK.md` · `specs/` (una spec por epic).
