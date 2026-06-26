"""
test_postgres_compat.py — Sensores del shim SQLite<->Postgres y guardas anti-regresion.

Corren en cualquier maquina sin Postgres (usan SQLite temporal o leen el codigo fuente).
El smoke real contra Postgres se activa solo si TEST_DATABASE_URL esta seteado
(apuntalo a una base/branch DE PRUEBA de Neon, nunca a produccion).

  python -m pytest tests/ -q
"""
import os
import re
from pathlib import Path

import pytest

import db

ROOT = Path(__file__).resolve().parent.parent
# Modulos top-level del proyecto (no tests, no scripts/)
PY_FILES = sorted(ROOT.glob("*.py"))


# --------------------------------------------------------------- shim _prep (unit)
def test_prep_insert_or_ignore():
    out = db._prep("INSERT OR IGNORE INTO t(a) VALUES (?)")
    assert "INSERT INTO t" in out
    assert "ON CONFLICT DO NOTHING" in out
    assert "?" not in out  # placeholder traducido a %s


def test_prep_placeholders():
    assert db._prep("SELECT * FROM t WHERE a=? AND b=?") == "SELECT * FROM t WHERE a=%s AND b=%s"


def test_prep_autoincrement():
    out = db._prep("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT)")
    assert "SERIAL PRIMARY KEY" in out
    assert "AUTOINCREMENT" not in out


def test_prep_no_double_on_conflict():
    sql = "INSERT OR IGNORE INTO t(a) VALUES (?) ON CONFLICT(a) DO NOTHING"
    assert db._prep(sql).lower().count("on conflict") == 1


# --------------------------------------------------- guardas anti-regresion (estaticas)
def test_no_lastrowid():
    """cur.lastrowid devuelve None en Postgres -> usar INSERT ... RETURNING id."""
    offenders = [p.name for p in PY_FILES
                 if ".lastrowid" in p.read_text(encoding="utf-8", errors="ignore")]
    assert not offenders, f"Reemplazar .lastrowid por 'INSERT ... RETURNING id' en: {offenders}"


def test_no_boolean_sum():
    """SUM(col = 'x') funciona en SQLite (1/0) pero falla en Postgres (SUM de boolean)."""
    pat = re.compile(r"SUM\s*\(\s*[A-Za-z_][\w.]*\s*=")
    offenders = [p.name for p in PY_FILES
                 if pat.search(p.read_text(encoding="utf-8", errors="ignore"))]
    assert not offenders, f"Usar SUM(CASE WHEN ... THEN 1 ELSE 0 END) en: {offenders}"


# --------------------------------------------------------- smoke SQLite (end to end)
@pytest.mark.parametrize("mod", ["db", "schema_v3", "usuarios", "kwstats"])
def test_modulo_importa(mod):
    """Un import roto = la app no arranca. Esto lo corta antes del deploy."""
    __import__(mod)


def test_init_db_y_roundtrip(tmp_path, monkeypatch):
    """Crea el schema real en SQLite temporal y hace un insert/select. No toca Neon."""
    monkeypatch.setattr(db, "DATABASE_URL", "")            # fuerza backend sqlite
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    assert db.backend() == "sqlite"
    db.init_db()
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "TEST-1", "nombre": "Prueba"})
    with db.conn() as c:
        r = c.execute(
            "SELECT codigo, nombre, estado_revision FROM licitaciones WHERE codigo=?",
            ("TEST-1",),
        ).fetchone()
    assert r["codigo"] == "TEST-1"
    assert r["estado_revision"] == "nueva"


# ------------------------------------------------- smoke real Postgres (opt-in)
@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="seteá TEST_DATABASE_URL (branch de prueba de Neon) para el smoke real contra Postgres",
)
def test_postgres_smoke(monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    assert db.backend() == "postgres"
    db.init_db()
    with db.conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO licitaciones"
            "(codigo,nombre,estado_revision,fecha_descubierta,fecha_actualizada)"
            " VALUES (?,?,?,?,?)",
            ("PGTEST-1", "x", "nueva", db._now(), db._now()),
        )
        r = c.execute("SELECT codigo FROM licitaciones WHERE codigo=?", ("PGTEST-1",)).fetchone()
    assert r["codigo"] == "PGTEST-1"
