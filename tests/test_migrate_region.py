"""
test_migrate_region.py — Guarda que la mudanza de región copie TODAS las tablas.

Si una tabla real no está en migrate_region.TABLES, esos datos se perderían silenciosamente
en la mudanza (ej. usuarios = logins, descartes = aprendizaje). Este test crea el esquema
completo y verifica que TABLES las cubra a todas.

  python -m pytest tests/test_migrate_region.py -q
"""
import db
import migrate_region
import schema_v2
import schema_v3


def test_tables_cubre_todo_el_esquema(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    schema_v3._MIGRATED.discard(str(tmp_path / "t.db"))
    db.init_db()
    schema_v2.migrate()
    schema_v3.migrate()

    with db.conn() as c:
        reales = {r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()}

    faltan = reales - set(migrate_region.TABLES)
    assert not faltan, f"migrate_region.TABLES NO incluye {faltan}: se perderían en la mudanza"
