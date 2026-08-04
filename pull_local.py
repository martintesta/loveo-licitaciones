"""
pull_local.py — Baja los datos de Neon a loveo.db (SQLite) local, para trabajar RÁPIDO en una sola
máquina (la app y la DB en el mismo disco: sin latencia de red). Neon queda como backup.

La foto de Neon MANDA: limpia cada tabla local y la reescribe con lo de Neon (idempotente).
Solo lectura sobre Neon; el set de tablas se toma del esquema local (fuente de verdad).

  python pull_local.py            # usa LOVEO_NEON_URL (o DATABASE_URL) como origen
"""
import os
import sqlite3

import psycopg

import db
import schema_v2
import schema_v3


def _neon_url():
    return (os.environ.get("LOVEO_NEON_URL") or os.environ.get("DATABASE_URL") or "").strip()


def main():
    url = _neon_url()
    if not url.startswith(("postgres://", "postgresql://")):
        raise SystemExit("Falta la URL de Neon (LOVEO_NEON_URL o DATABASE_URL en el entorno).")

    # 1) Esquema local (forzar SQLite aunque DATABASE_URL apunte a Neon)
    db.DATABASE_URL = ""
    db.init_db()
    schema_v2.migrate()
    schema_v3.migrate()

    # 2) El set de tablas = el del esquema local (así no dependemos de una lista hardcodeada)
    dst = sqlite3.connect(str(db.DB_PATH))
    dst.row_factory = sqlite3.Row
    dst.execute("PRAGMA foreign_keys=OFF")     # copia cruda: el orden de tablas no importa
    tablas = [r["name"] for r in dst.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]

    src = psycopg.connect(url, autocommit=True)   # solo lectura; autocommit evita estado de transacción
    total = 0
    for t in tablas:
        try:
            cur = src.execute(f"SELECT * FROM {t}")
        except Exception:
            print(f"  {t}: (no existe en Neon, salteado)")
            continue
        cols = [d.name for d in cur.description]
        rows = cur.fetchall()
        dst.execute(f"DELETE FROM {t}")           # la foto de Neon reemplaza lo local
        if rows:
            ph = ", ".join(["?"] * len(cols))
            collist = ", ".join(cols)
            dst.executemany(f"INSERT INTO {t} ({collist}) VALUES ({ph})", [tuple(r) for r in rows])
        dst.commit()
        total += len(rows)
        print(f"  {t}: {len(rows)}")
    src.close()
    dst.close()
    print(f"OK · {total} filas bajadas de Neon a {db.DB_PATH}.")


if __name__ == "__main__":
    main()
