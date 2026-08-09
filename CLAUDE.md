# loveo-licitaciones — reglas del proyecto

Pipeline de licitaciones públicas (Mercado Público / ChileCompra) para **Loveo Construcciones**
(construcción modular en acero: contenedores, módulos, baños/salas modulares, REAS/RESPEL, paneles
solares; bases en Pirque + Puerto Montt). App interna (H1) con futuro SaaS (H2).

## Stack
- **Python 3.11**, **Streamlit** (tablero), **psycopg 3** (Postgres) / **sqlite3** (default).
- Capas: **A** descubrir/scorear (API ChileCompra) · **B** descargar bases (worker IP residencial, fuera de Render) · **C** Claude lee bases → extracción → score.
- Datos: **SQLite** local (default) ↔ **Postgres/Neon** en prod, vía `DATABASE_URL`. El shim vive en `db.py`.

## Comandos
```bash
streamlit run tablero3.py            # levantar el tablero (puerto 8502 local)
python scripts/preflight.py          # sensores BLOQUEANTES: secretos + ruff + pytest
python scripts/review.py             # reviewer ADVERSARIAL del diff (advisory, no bloquea)
python -m pytest tests/ -q           # solo tests
python usuarios.py passwd <user>     # cambiar contraseña (pega contra la base activa)
python schema_v3.py                  # aplicar migraciones (idempotente)
python informe.py <codigo>           # análisis integral (8-9 hojas) → carpeta de bases + stdout
python consolidado.py                # tablero del lote vigente (sin IA, sin costo de tokens)
python precios.py vencidos           # qué materiales toca re-cotizar (gratis)
python precios.py refrescar          # refresco del catálogo (lo corre solo la tarea mensual)
python precios.py corregir "<desc>" 3200000 --url <link> --nota "<de dónde salió>"
```

## Cómo trabajamos (spec → sensores → loop)
1. **Spec primero**: antes de codear, copiar `specs/_templates/` a `specs/<feature>/` y llenar
   SPEC (qué/criterios de aceptación con comando) + PHASES (fases con su sensor). La spec viva de
   H1 está en `specs/h1-produccion/`.
2. **Sensores**: `scripts/preflight.py` (bloqueante, corre solo en el pre-push) decide "listo",
   no la palabra del agente. `scripts/review.py` (adversarial, advisory) se corre antes de mergear
   y sus hallazgos los juzga un humano (puede dar falsos positivos: conocimiento desactualizado de
   model IDs, contexto de `db.py` que no ve, etc.).
3. **Cerrar**: cuando una fase pasa, anotarla en `specs/<feature>/DONE.md` (fecha + commit + cómo se verificó).

## Criterio de "listo" (exit 0, nadie marca el check a mano)
Un cambio está terminado cuando `python scripts/preflight.py` devuelve 0. Eso corre, en orden:
1. **escáner de secretos** sobre archivos trackeados,
2. **ruff** (errores reales, no estilo),
3. **pytest**.
El hook `.git/hooks/pre-push` corre esto y **bloquea el push** si algo falla.
Tras clonar el repo: `python scripts/preflight.py --install-hook` (los hooks no se clonan).

## INVARIANTES — no romper (cada uno ya costó un bug)
- **Postgres vs SQLite**: todo SQL pasa por `db.conn()`. IDs nuevos → `INSERT ... RETURNING id`, **nunca** `cur.lastrowid` (es `None` en PG). Conteos de booleanos → `SUM(CASE WHEN x THEN 1 ELSE 0 END)`, **nunca** `SUM(x = 'y')` (PG no suma booleanos). `tests/test_postgres_compat.py` guarda estas dos.
- **Cash flow** usa el campo **`Modalidad`** (catálogo), **no** `TipoPago`. El comportamiento de pago del comprador vive en la Ficha Comprador, detrás de WAF (403 desde datacenter).
- **El score es PROVISIONAL** hasta la cubicación real de Valentina. Las vistas no inventan nada: un código MP real lleva solo su data real.
- **Secretos**: el ticket de ChileCompra va en **`.env`** (`LOVEO_CHILECOMPRA_TICKET`), jamás en `config_local.py`. **Nunca** sobrescribir ni commitear `.env`, `config_local.py`, `credentials/`, `service_account.json`, `token.json` (todos gitignored). `config_local.py` tiene las keywords competitivas → se mantiene fuera de git.
- **Capa B y Ficha Comprador** están bloqueadas por WAF desde IP de datacenter → requieren worker con IP residencial chilena. La UI hosteada (Render) anda en cloud; solo el worker necesita IP CL.
- **Modelo LLM**: `LOVEO_MODEL` (default `claude-haiku-4-5`) lo leen Capa C, asistente (text-to-SQL) y `/kw eval`. Barato para lectura masiva. Subir a `claude-sonnet-4-6` solo si el análisis lo amerita — vía env var, sin tocar código. El **análisis integral** usa su propia var, `LOVEO_MODEL_ANALISIS` (default `claude-opus-5`): es una sola llamada por licitación sobre el digest completo, ahí el modelo bueno se paga solo.
- **El Excel del análisis integral es un MODELO, no un reporte**: las celdas derivadas son fórmulas encadenadas (Cubicación → Financiero → Resumen). Si tocás `excel_analisis.py`, el sensor que manda es `tests/test_excel_analisis.py::test_editar_la_cantidad_recalcula_toda_la_cadena` — **ejecuta** las fórmulas con el motor `formulas`, no las mira como strings. Pegar un valor calculado en Python donde iba una fórmula rompe el producto sin romper ningún test de texto.
- **Los precios no se inventan**: la cubicación del análisis se precia contra `precios_referencia` (lo que Loveo realmente pagó). Lo que no tiene precio se declara en INFO FALTANTE; nunca se completa con lo que el modelo recuerde.
- **`precios_referencia` es APPEND-ONLY**: cada cotización es un punto nuevo con fecha **y hora** + `fuente` + `source_url` (el link). Nunca hacer `UPDATE` sobre un precio: se perdería el historial y la tendencia. El "precio vigente" es el último punto (`precios.catalogo()`). Una sola cotizadora web para todo el proyecto: `precios.buscar_precio_web` (cubicacion_ia delega ahí).

## Antipatterns a evitar
- Truncar inputs en silencio (PDFs, bases) — avisar y chunkear, no recortar callado.
- Tocar `config_local.py` / `.env` "para probar algo".
- Declarar "listo" sin que `preflight.py` dé 0.
- SQL nuevo sin pensar el caso Postgres (ver invariantes).

## Deploy
- **Render** (Docker, plan free) conectado a GitHub; redeploy automático en cada push a `master`.
- Base en **Neon** (Postgres) vía `DATABASE_URL`. Vars en Render → Environment: `DATABASE_URL`, `ANTHROPIC_API_KEY`, `LOVEO_CHILECOMPRA_TICKET`, `LOVEO_MODEL`.
- Tema del login: `.streamlit/config.toml` fuerza tema claro (sin él, Streamlit lava los colores).
- Detalle en `DEPLOY.md`.
