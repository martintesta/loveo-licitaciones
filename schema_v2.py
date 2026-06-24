"""
schema_v2.py — Migración de datos (idempotente) que habilita las vistas del tablero
con DATA REAL: Inteligencia competitiva, Desiertas/re-licitación, Seguimiento de Competencia.

Tablas nuevas (FK a licitaciones.codigo):
  adjudicaciones   — cabecera del bloque Adjudicacion (fecha, n° oferentes, url acta)
  items            — líneas (Items.Listado) con su adjudicación: producto, cantidad, ganador, $ unit
  competidores     — registro derivado por RUT (razón social, contacto, desde)
  participaciones  — RUT × licitación × resultado (ganada/perdida) × monto × año
  relicitaciones   — enlace desierta original → re-licitación

Correr:  python schema_v2.py
"""
import db


def migrate():
    db.init_db()
    with db.conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS adjudicaciones (
            codigo        TEXT PRIMARY KEY REFERENCES licitaciones(codigo) ON DELETE CASCADE,
            fecha         TEXT,
            numero        TEXT,
            n_oferentes   INTEGER,
            url_acta      TEXT
        );

        CREATE TABLE IF NOT EXISTS items (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo          TEXT NOT NULL REFERENCES licitaciones(codigo) ON DELETE CASCADE,
            nombre_producto TEXT,
            cantidad        REAL,
            unidad          TEXT,
            rut_proveedor   TEXT,      -- ganador del ítem (si adjudicado)
            nombre_proveedor TEXT,
            monto_unitario  REAL,
            monto_total     REAL
        );

        CREATE TABLE IF NOT EXISTS competidores (
            rut          TEXT PRIMARY KEY,
            razon_social TEXT,
            contacto     TEXT,          -- NO viene de la API de adjudicación: lookup/manual (queda NULL)
            desde_anio   INTEGER
        );

        CREATE TABLE IF NOT EXISTS participaciones (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            rut       TEXT NOT NULL REFERENCES competidores(rut) ON DELETE CASCADE,
            codigo    TEXT NOT NULL REFERENCES licitaciones(codigo) ON DELETE CASCADE,
            resultado TEXT,             -- 'ganada' | 'perdida' (perdidas requieren ofertas públicas: futuro)
            monto     REAL,
            anio      INTEGER,
            UNIQUE(rut, codigo)
        );

        CREATE TABLE IF NOT EXISTS relicitaciones (
            codigo_desierto TEXT NOT NULL REFERENCES licitaciones(codigo) ON DELETE CASCADE,
            codigo_nueva    TEXT NOT NULL,
            score_match     REAL,
            PRIMARY KEY (codigo_desierto, codigo_nueva)
        );

        CREATE INDEX IF NOT EXISTS idx_items_codigo  ON items(codigo);
        CREATE INDEX IF NOT EXISTS idx_items_rut     ON items(rut_proveedor);
        CREATE INDEX IF NOT EXISTS idx_part_rut      ON participaciones(rut);
        CREATE INDEX IF NOT EXISTS idx_part_anio     ON participaciones(anio);
        """)
    print("Migración v2 aplicada: adjudicaciones, items, competidores, participaciones, relicitaciones.")


if __name__ == "__main__":
    migrate()
