"""
schema_v3.py — Migración v3: costos y cubicación (Margen).

Tablas:
  cubicaciones        — cabecera por proyecto/licitación (ingresos, costo total, margen).
  cubicacion_items    — itemizado (partida, grupo, descripción, cantidad, unidad, precio, total, devengado).
  precios_referencia  — catálogo de precios por elemento (fuente: valentina/adjudicacion/web) → cubicación tipo + trazabilidad.

Idempotente. Origen del dato: el Excel de cubicación de Valentina (ver cubicacion.py) y, a futuro,
adjudicaciones reales (items) y búsqueda web.

  python schema_v3.py
"""
import threading

import db


_MIGRATED = set()
_LOCK = threading.Lock()


def migrate():
    """Idempotente: crea las tablas v3 y agrega columnas faltantes a `documentos`. Sin print.

    Cacheado por proceso y por base (clave = DATABASE_URL o ruta sqlite): el DDL son decenas de
    statements y migrate() se llama desde muchos lados; correrlo en CADA request contra Neon
    cross-continente es carísimo. Un nuevo deploy reinicia el proceso y lo vuelve a correr.
    Tests: cada base temporal es una clave distinta, así que igual migran."""
    key = db.DATABASE_URL or str(db.DB_PATH)
    if key in _MIGRATED:                       # fast-path sin lock
        return
    with _LOCK:
        if key in _MIGRATED:                   # double-check (sesiones concurrentes de Streamlit)
            return
        _crear_tablas()
        _MIGRATED.add(key)


def _crear_tablas():
    db.init_db()
    with db.conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS cubicaciones (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            proyecto        TEXT NOT NULL,
            codigo          TEXT,                 -- licitación asociada (opcional)
            archivo         TEXT,                 -- nombre del Excel fuente
            ingreso_con_iva REAL,
            ingreso_sin_iva REAL,
            costo_total     REAL,
            margen          REAL,                 -- ingreso_sin_iva - costo_total
            margen_pct      REAL,
            origen          TEXT DEFAULT 'valentina',  -- valentina | tipo
            fecha           TEXT,                 -- fecha de ingestión
            version         TEXT,
            UNIQUE(proyecto, archivo)
        );

        CREATE TABLE IF NOT EXISTS cubicacion_items (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            cubicacion_id   INTEGER NOT NULL REFERENCES cubicaciones(id) ON DELETE CASCADE,
            partida         TEXT,                 -- col B (Estructura Acero, MANO DE OBRA, …)
            grupo           TEXT,                 -- material | mano_obra | transporte | otros
            descripcion     TEXT,
            cantidad        REAL,
            unidad          TEXT,
            precio_unitario REAL,
            total           REAL,
            precio_fuente   TEXT,                 -- interno | web | manual (de dónde salió el precio)
            precio_url      TEXT,                 -- referencia clickeable (ecommerce) si fuente=web
            devengado       REAL,
            estado_pago     TEXT
        );

        CREATE TABLE IF NOT EXISTS precios_referencia (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            descripcion      TEXT NOT NULL,
            descripcion_norm TEXT,                -- normalizada (sin acentos, minúsculas) para matching
            unidad           TEXT,
            precio_unitario  REAL,
            fuente           TEXT,                -- valentina | adjudicacion | web
            source_url       TEXT,                -- referencia clickeable (ecommerce) si fuente=web
            proyecto         TEXT,
            region           TEXT,
            fecha            TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_cub_items_cub  ON cubicacion_items(cubicacion_id);
        CREATE INDEX IF NOT EXISTS idx_cub_items_grp  ON cubicacion_items(grupo);
        CREATE TABLE IF NOT EXISTS sesiones (
            token     TEXT PRIMARY KEY,
            username  TEXT NOT NULL,
            expira    TEXT,
            creado_at TEXT
        );

        CREATE TABLE IF NOT EXISTS usuarios (
            username  TEXT PRIMARY KEY,
            nombre    TEXT,
            rol       TEXT DEFAULT 'analista',   -- admin | analista
            salt      TEXT,
            pass_hash TEXT,
            activo    INTEGER DEFAULT 1,
            creado_at TEXT
        );

        CREATE TABLE IF NOT EXISTS keywords (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            termino   TEXT NOT NULL,
            tipo      TEXT NOT NULL DEFAULT 'incluir',   -- incluir | excluir | amplio
            origen    TEXT DEFAULT 'manual',             -- manual | aprendida | sugerida | seed
            activo    INTEGER DEFAULT 1,
            nota      TEXT,
            creado_at TEXT,
            UNIQUE(termino, tipo)
        );

        CREATE TABLE IF NOT EXISTS licitacion_keywords (
            codigo  TEXT NOT NULL,
            termino TEXT NOT NULL,
            tipo    TEXT,
            PRIMARY KEY (codigo, termino)
        );

        CREATE TABLE IF NOT EXISTS descartes (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo    TEXT NOT NULL,
            categoria TEXT,                          -- clave en feedback.CATEGORIAS
            tipo      TEXT,                          -- calidad | operativo
            motivo    TEXT,
            ts        TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS resultados (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo    TEXT NOT NULL,
            resultado TEXT,                          -- ganada | perdida | desierta
            categoria TEXT,                          -- clave en feedback.RESULTADO_CATEGORIAS
            impacto   TEXT,                          -- positivo | malfit | competida | neutro
            motivo    TEXT,
            ts        TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS analisis_bases (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo          TEXT NOT NULL,
            ts              TEXT,
            modelo          TEXT,
            resumen         TEXT,
            presupuesto_clp REAL,
            plazo_dias      INTEGER,
            json_extraccion TEXT,
            score_antes     INTEGER,
            score_despues   INTEGER
        );

        CREATE TABLE IF NOT EXISTS errores (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT,
            contexto  TEXT,                        -- app | worker | run_daily | ...
            mensaje   TEXT,
            traceback TEXT,
            resuelto  INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS worker_estado (
            id             INTEGER PRIMARY KEY,       -- siempre 1 (fila única)
            ultimo_ok      TEXT,                      -- última pasada SANA (bajó algo o backlog=0)
            ultimo_intento TEXT,                      -- última pasada (haya funcionado o no)
            pendientes     INTEGER,                   -- backlog de Capa B al inicio de la pasada
            bajadas        INTEGER,
            capac          INTEGER,
            muro           INTEGER DEFAULT 0          -- 1 si chocó con el muro anti-bot
        );

        CREATE TABLE IF NOT EXISTS notificaciones (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo       TEXT,
            tipo         TEXT,                        -- cierre | visita
            fecha_evento TEXT,                        -- deadline notificado (si cambia -> re-notifica)
            canal        TEXT,                        -- email | ...
            enviado_at   TEXT
        );

        CREATE TABLE IF NOT EXISTS reputacion_comprador (
            organismo TEXT PRIMARY KEY,               -- comprador (NombreOrganismo)
            nivel     TEXT NOT NULL CHECK (nivel IN ('buena','regular','mala')),
            nota      TEXT,
            fuente    TEXT DEFAULT 'manual',           -- manual | ficha_comprador (futuro worker)
            ts        TEXT
        );

        CREATE TABLE IF NOT EXISTS recall_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo    TEXT,
            nombre    TEXT,
            fecha_run TEXT,                          -- ddmmaaaa del run de discovery
            bucket    TEXT,                          -- recall | excluido (ver recall.py)
            kw        TEXT,                          -- término(s) que explican el bucket
            estado    TEXT DEFAULT 'pendiente',      -- pendiente | promovida | descartada
            ts        TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_precios_norm   ON precios_referencia(descripcion_norm);
        CREATE INDEX IF NOT EXISTS idx_precios_fuente ON precios_referencia(fuente);
        CREATE INDEX IF NOT EXISTS idx_analisis_cod   ON analisis_bases(codigo);
        CREATE INDEX IF NOT EXISTS idx_descartes_cat  ON descartes(categoria);
        CREATE INDEX IF NOT EXISTS idx_resultados_cat ON resultados(categoria);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_recall_cod_run ON recall_log(codigo, fecha_run);
        CREATE INDEX IF NOT EXISTS idx_recall_estado ON recall_log(estado);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_notif_cod_tipo_fecha
            ON notificaciones(codigo, tipo, fecha_evento);
        """)
        # documentos: en SQLite viejo puede faltar fuente/url → ALTER (PRAGMA es SQLite-only).
        # En Postgres las columnas ya vienen del CREATE de db.py.
        if db.backend() == "sqlite":
            cols = [r[1] for r in c.execute("PRAGMA table_info(documentos)")]
            if "fuente" not in cols:
                c.execute("ALTER TABLE documentos ADD COLUMN fuente TEXT")
            if "url" not in cols:
                c.execute("ALTER TABLE documentos ADD COLUMN url TEXT")
        # Precios/cubicación (Fase 3): columnas nuevas sobre tablas ya creadas en prod → ALTER idempotente.
        _asegurar_columna(c, "cubicacion_items", "precio_fuente", "TEXT")
        _asegurar_columna(c, "cubicacion_items", "precio_url", "TEXT")
        _asegurar_columna(c, "precios_referencia", "source_url", "TEXT")


def _asegurar_columna(c, tabla, columna, tipo):
    """Agrega una columna si falta, en SQLite (PRAGMA) y Postgres (ADD COLUMN IF NOT EXISTS)."""
    if db.backend() == "sqlite":
        cols = [r[1] for r in c.execute(f"PRAGMA table_info({tabla})")]
        if columna not in cols:
            c.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}")
    else:
        c.execute(f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS {columna} {tipo}")


def main():
    migrate()
    print("Migración v3 aplicada: cubicaciones, cubicacion_items, precios_referencia, documentos(fuente,url).")


if __name__ == "__main__":
    main()
