"""
test_competencia_kwstats.py — Smoke de las queries que tocaron el bug SUM(boolean) en Postgres.

competencia.resumen() y kwstats.stats() usan SUM(CASE WHEN ... THEN 1 ELSE 0 END). Este smoke
las corre (contra sqlite, pero el guard estático + el smoke real de CI cubren Postgres) y
verifica que devuelven la forma esperada sin reventar.

  python -m pytest tests/test_competencia_kwstats.py -q
"""
import db
import schema_v2
import schema_v3


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v2.migrate()
    schema_v3.migrate()


def test_competencia_resumen_corre(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    import competencia
    r = competencia.resumen()
    assert isinstance(r, (list, dict))


def test_kwstats_backfill_y_stats_corren(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    import kwstats
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "L1", "nombre": "Contenedor modular"})
    kwstats.backfill()
    s = kwstats.stats()
    assert isinstance(s, (list, dict))
