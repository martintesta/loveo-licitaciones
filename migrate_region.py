"""
migrate_region.py — Copia TODA la base de un Postgres a otro (mudanza de región de Neon).

Caso: mover la base de Neon de Sudamérica a us-west-2 (Oregon), junto a Render, para matar la
latencia cross-continente. No se puede cambiar la región de un proyecto Neon existente -> hay que
crear uno nuevo en Oregon y copiar los datos.

Uso (con AMBAS URLs en el entorno; la nueva es la de Oregon):
  OLD_DATABASE_URL=postgresql://...sa...   NEW_DATABASE_URL=postgresql://...us-west-2...   \
      python migrate_region.py

Qué hace: crea el esquema completo en la base NUEVA (idempotente), copia tabla por tabla
(padres primero, ON CONFLICT DO NOTHING para ser re-ejecutable) y resetea las secuencias.
Solo lectura sobre la base vieja. Re-ejecutable sin duplicar.
"""
import os

import psycopg
from psycopg import sql

import db
import schema_v2
import schema_v3

# Orden: padres antes que hijos (FK). Lista COMPLETA — incluye auth y aprendizaje.
TABLES = [
    "usuarios", "sesiones", "runs", "keywords",
    "licitaciones",
    "eventos", "documentos", "adjudicaciones", "items",
    "competidores", "participaciones", "relicitaciones",
    "descartes", "resultados", "licitacion_keywords", "analisis_bases",
    "cubicaciones", "cubicacion_items", "precios_referencia", "recall_log",
]


def main():
    old = os.environ.get("OLD_DATABASE_URL", "").strip()
    new = os.environ.get("NEW_DATABASE_URL", "").strip()
    if not (old.startswith("postgres") and new.startswith("postgres")):
        raise SystemExit("Seteá OLD_DATABASE_URL y NEW_DATABASE_URL (ambas postgres).")
    if old == new:
        raise SystemExit("OLD y NEW son la misma base. Abortando.")

    # 1) Esquema completo en la base NUEVA (apuntamos db a NEW e invocamos las migraciones).
    db.DATABASE_URL = new
    schema_v3._MIGRATED.discard(new)
    db.init_db()
    schema_v2.migrate()
    schema_v3.migrate()
    print("Esquema creado en la base nueva.")

    # 2) Copia tabla por tabla (vieja -> nueva), re-ejecutable.
    src = psycopg.connect(old, row_factory=psycopg.rows.dict_row)
    src.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ  # snapshot consistente del origen
    dst = psycopg.connect(new)
    total = 0
    for t in TABLES:
        try:
            rows = src.execute(sql.SQL("SELECT * FROM {}").format(sql.Identifier(t))).fetchall()
        except Exception as e:
            print(f"  {t}: (no existe en origen / error: {e})")
            continue
        if not rows:
            print(f"  {t}: 0")
            continue
        cols = list(rows[0].keys())
        data = [tuple(r[c] for c in cols) for r in rows]
        ins = sql.SQL("INSERT INTO {tbl} ({cols}) VALUES ({ph}) ON CONFLICT DO NOTHING").format(
            tbl=sql.Identifier(t),
            cols=sql.SQL(", ").join(map(sql.Identifier, cols)),
            ph=sql.SQL(", ").join([sql.Placeholder()] * len(cols)),
        )
        with dst.cursor() as cur:
            cur.executemany(ins, data)
        dst.commit()
        total += len(rows)
        print(f"  {t}: {len(rows)}")

    # 3) Resetear las secuencias de los id serial (las inserciones explícitas no las avanzan).
    for t in TABLES:
        try:
            with dst.cursor() as cur:
                cur.execute(sql.SQL(
                    "SELECT setval(pg_get_serial_sequence({tname},'id'), "
                    "COALESCE((SELECT MAX(id) FROM {tbl}), 1), true)").format(
                        tname=sql.Literal(t), tbl=sql.Identifier(t)))
            dst.commit()
        except Exception:
            dst.rollback()  # tabla sin columna id serial -> ignorar

    src.close()
    dst.close()
    print(f"OK · {total} filas copiadas a la base nueva (Oregon).")


if __name__ == "__main__":
    main()
