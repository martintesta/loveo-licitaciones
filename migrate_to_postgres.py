"""
migrate_to_postgres.py — Copia los datos de loveo.db (SQLite) al Postgres de DATABASE_URL.

Uso (con el Postgres destino en el entorno):
  DATABASE_URL=postgresql://...  python migrate_to_postgres.py

Qué hace: asegura el esquema en Postgres (idempotente), copia tabla por tabla (parents primero,
ON CONFLICT DO NOTHING para ser re-ejecutable), y resetea las secuencias de los id autoincrementales.
Solo lectura sobre SQLite; no toca el origen.
"""
import os
import sqlite3
import psycopg
import db
import schema_v2
import schema_v3

# Orden: padres antes que hijos (por las FK). Fuente ÚNICA: migrate_region.TABLES — antes había una
# lista propia más corta y este script (el que siembra el deploy) migraba SIN usuarios, keywords,
# descartes/resultados, recall_log, plan_feedback, etc.
from migrate_region import TABLES


def main():
    url = os.environ.get("DATABASE_URL", "")
    if db.backend() != "postgres":
        raise SystemExit("Seteá DATABASE_URL al Postgres destino antes de correr esto.")

    # 1) Esquema en Postgres (idempotente)
    db.init_db()
    schema_v2.migrate()
    schema_v3.migrate()

    # 2) Origen SQLite (directo, sin pasar por db.conn que ahora apunta a PG)
    src = sqlite3.connect(str(db.DB_PATH))
    src.row_factory = sqlite3.Row

    dst = psycopg.connect(url)
    total = 0
    for t in TABLES:
        try:
            rows = src.execute(f"SELECT * FROM {t}").fetchall()
        except sqlite3.OperationalError:
            print(f"  {t}: (no existe en SQLite, salteado)")
            continue
        if not rows:
            print(f"  {t}: 0")
            continue
        cols = list(rows[0].keys())
        collist = ", ".join(cols)
        ph = ", ".join(["%s"] * len(cols))
        data = [tuple(r[c] for c in cols) for r in rows]
        with dst.cursor() as cur:
            cur.executemany(f"INSERT INTO {t} ({collist}) VALUES ({ph}) ON CONFLICT DO NOTHING", data)
        dst.commit()
        total += len(rows)
        print(f"  {t}: {len(rows)}")

    # 3) Resetear secuencias de los id (las inserciones explícitas no avanzan el serial)
    for t in TABLES:
        try:
            with dst.cursor() as cur:
                cur.execute(
                    f"SELECT setval(pg_get_serial_sequence('{t}','id'), "
                    f"COALESCE((SELECT MAX(id) FROM {t}), 1), true)")
            dst.commit()
        except Exception:
            dst.rollback()  # tabla sin columna id serial → ignorar

    dst.close()
    src.close()
    print(f"OK · {total} filas migradas a Postgres.")


if __name__ == "__main__":
    main()
