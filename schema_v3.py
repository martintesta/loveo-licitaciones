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
import db


def migrate():
    """Idempotente: crea las tablas v3 y agrega columnas faltantes a `documentos`. Sin print."""
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

        CREATE INDEX IF NOT EXISTS idx_precios_norm   ON precios_referencia(descripcion_norm);
        CREATE INDEX IF NOT EXISTS idx_precios_fuente ON precios_referencia(fuente);
        CREATE INDEX IF NOT EXISTS idx_analisis_cod   ON analisis_bases(codigo);
        CREATE INDEX IF NOT EXISTS idx_descartes_cat  ON descartes(categoria);
        """)
        # documentos: en SQLite viejo puede faltar fuente/url → ALTER (PRAGMA es SQLite-only).
        # En Postgres las columnas ya vienen del CREATE de db.py.
        if db.backend() == "sqlite":
            cols = [r[1] for r in c.execute("PRAGMA table_info(documentos)")]
            if "fuente" not in cols:
                c.execute("ALTER TABLE documentos ADD COLUMN fuente TEXT")
            if "url" not in cols:
                c.execute("ALTER TABLE documentos ADD COLUMN url TEXT")


def main():
    migrate()
    print("Migración v3 aplicada: cubicaciones, cubicacion_items, precios_referencia, documentos(fuente,url).")


if __name__ == "__main__":
    main()
