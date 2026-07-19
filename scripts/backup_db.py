"""
backup_db.py — Backup de la base (endurecer operación, #5). Corré por cron/Task Scheduler.

Postgres (Neon): `pg_dump` → un .sql comprimible en ./backups/. SQLite: copia el archivo.
Neon además tiene branching + PITR; esto es un respaldo lógico portable extra (y para dev/local).

  python scripts/backup_db.py                 # a ./backups/loveo-<ts>.sql|.db
  python scripts/backup_db.py --dir /ruta     # a otra carpeta
  BACKUP_KEEP=14 python scripts/backup_db.py   # retiene los últimos 14 (default 14)

Requiere el binario `pg_dump` para Postgres (viene con el cliente de PostgreSQL).
No imprime la URL ni credenciales.
"""
import os
import sys
import shutil
import pathlib
import datetime
import subprocess
from urllib.parse import urlparse, parse_qs, unquote

ROOT = pathlib.Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

import config  # noqa: E402,F401  (carga .env para credenciales; db igual lo hace)
import db      # noqa: E402


def _destino(dirbackup):
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    ext = "sql" if db.backend() == "postgres" else "db"
    d = pathlib.Path(dirbackup)
    d.mkdir(parents=True, exist_ok=True)
    return d / f"loveo-{ts}.{ext}"


def _retener(dirbackup, keep):
    files = sorted(pathlib.Path(dirbackup).glob("loveo-*"), reverse=True)
    for viejo in files[keep:]:
        try:
            viejo.unlink()
        except OSError:
            pass


def backup(dirbackup="backups"):
    destino = _destino(dirbackup)
    if db.backend() == "postgres":
        if not shutil.which("pg_dump"):
            print("[FALTA] pg_dump no está instalado (viene con el cliente de PostgreSQL).")
            return 1
        # La password NO va en argv (visible por `ps`): va en PGPASSWORD del entorno del hijo.
        u = urlparse(db.DATABASE_URL)
        env = dict(os.environ)
        if u.password:
            env["PGPASSWORD"] = unquote(u.password)   # urlparse no decodifica el userinfo (%40 → @)
        env.setdefault("PGSSLMODE", (parse_qs(u.query).get("sslmode", ["require"])[0]))  # Neon exige SSL
        cmd = ["pg_dump", "-h", u.hostname or "localhost", "-p", str(u.port or 5432),
               "-U", unquote(u.username or ""), "-d", (u.path or "").lstrip("/")]
        with open(destino, "wb") as f:
            r = subprocess.run(cmd, env=env, stdout=f, stderr=subprocess.PIPE)
        if r.returncode != 0:
            print(f"[FAIL] pg_dump: {r.stderr.decode('utf-8', 'replace')[:400]}")
            destino.unlink(missing_ok=True)
            return 1
    else:
        if not db.DB_PATH.exists():
            print(f"[FALTA] no existe la base local {db.DB_PATH}.")
            return 1
        shutil.copy2(db.DB_PATH, destino)
    mb = destino.stat().st_size / 1e6
    print(f"[ok] backup ({db.backend()}) → {destino} ({mb:.1f} MB)")
    _retener(dirbackup, int(os.environ.get("BACKUP_KEEP", "14")))
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    dirb = args[args.index("--dir") + 1] if "--dir" in args else "backups"
    sys.exit(backup(dirb))
