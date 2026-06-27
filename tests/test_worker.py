"""
test_worker.py — Sensor del loop del worker residencial (Capa B).

Prueba la ORQUESTACIÓN (poll → procesar → estado) sin Playwright ni IP chilena: la
función de descarga se inyecta (mock). Contra SQLite temporal (no toca Neon).

  python -m pytest tests/test_worker.py -q
"""
import db
import worker


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()


def test_pendientes_solo_admisibles_pendientes(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "A", "nombre": "x"})
        db.upsert_licitacion(c, {"codigo": "B", "nombre": "y"})
        db.set_admisibilidad(c, "A", True, "ok", True)    # admisible + docs pendiente (default)
        db.set_admisibilidad(c, "B", False, "no", False)  # no admisible -> fuera
        db.upsert_licitacion(c, {"codigo": "C", "nombre": "z"})
        db.set_admisibilidad(c, "C", True, "ok", True)    # admisible PERO...
        c.execute("UPDATE licitaciones SET docs_estado='descargado' WHERE codigo=?", ("C",))  # ...ya bajado -> fuera
    assert worker.pendientes() == ["A"]


def test_procesar_exito(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "A", "nombre": "x"})
    assert worker.procesar("A", lambda cod: True) is True


def test_procesar_error_marca_estado_y_traza(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "A", "nombre": "x"})

    def _boom(cod):
        raise RuntimeError("playwright se cayó")

    assert worker.procesar("A", _boom) is False
    with db.conn() as c:
        estado = c.execute("SELECT docs_estado FROM licitaciones WHERE codigo=?", ("A",)).fetchone()
        ev = c.execute("SELECT 1 FROM eventos WHERE codigo='A' AND tipo='error'").fetchone()
    assert estado["docs_estado"] == "error"
    assert ev is not None


def test_una_pasada_cuenta_procesadas(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "A", "nombre": "x"})
        db.set_admisibilidad(c, "A", True, "ok", True)
    r = worker.una_pasada(descargar=lambda cod: True)
    assert r == {"pendientes": 1, "procesadas": 1}
