"""
test_worker.py — Sensor del loop del worker residencial (Capa B).

Prueba la ORQUESTACIÓN (poll → procesar → estado) sin Playwright ni IP chilena: la
función de descarga se inyecta (mock). Contra SQLite temporal (no toca Neon).

  python -m pytest tests/test_worker.py -q
"""
import ast
import pathlib

import db
import worker


def test_worker_importa_config_antes_que_db():
    """Regresión operativa: worker debe importar `config` (que carga .env) ANTES que `db`, porque
    db lee DATABASE_URL en su import. Sin este orden, `python worker.py` en la máquina residencial
    caería a SQLite local en vez de Neon y poliría una base vacía en silencio."""
    ruta = pathlib.Path(__file__).resolve().parent.parent / "worker.py"
    orden = []
    for node in ast.parse(ruta.read_text(encoding="utf-8")).body:   # solo imports top-level, en orden
        if isinstance(node, ast.Import):
            orden.extend(a.name for a in node.names)
    assert "config" in orden, "worker.py debe importar config (carga .env)"
    assert orden.index("config") < orden.index("db"), "config debe importarse antes que db"


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
    # con_capac=False: probamos SOLO la etapa de descarga (Capa B), sin tocar Claude.
    r = worker.una_pasada(descargar=lambda cod: True, con_capac=False)
    assert r == {"pendientes": 1, "procesadas": 1, "capac": 0}


# ---------------------------------------------------------------- Capa C encadenada (Fase worker)
def _bajada_sin_analisis(tmp_path, monkeypatch, codigo):
    """Deja una lic con bases 'descargado' pero sin fila en analisis_bases → lista para Capa C."""
    import schema_v3
    _setup(tmp_path, monkeypatch)
    schema_v3.migrate()  # crea analisis_bases
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": codigo, "nombre": "x"})
        db.set_admisibilidad(c, codigo, True, "ok", True)
        c.execute("UPDATE licitaciones SET docs_estado='descargado' WHERE codigo=?", (codigo,))


def test_pendientes_capac_solo_bajadas_sin_analisis(tmp_path, monkeypatch):
    _bajada_sin_analisis(tmp_path, monkeypatch, "A")
    with db.conn() as c:
        # B bajada Y ya analizada -> fuera; C pendiente de bajar -> fuera
        db.upsert_licitacion(c, {"codigo": "B", "nombre": "y"})
        c.execute("UPDATE licitaciones SET docs_estado='descargado' WHERE codigo=?", ("B",))
        c.execute("INSERT INTO analisis_bases (codigo, ts) VALUES (?, ?)", ("B", "2026-01-01"))
        db.upsert_licitacion(c, {"codigo": "C", "nombre": "z"})  # docs_estado='pendiente'
        # D bajada PERO no admisible -> fuera (no gastamos tokens en algo que no vamos a presentar)
        db.upsert_licitacion(c, {"codigo": "D", "nombre": "w"})
        db.set_admisibilidad(c, "D", False, "no", False)
        c.execute("UPDATE licitaciones SET docs_estado='descargado' WHERE codigo=?", ("D",))
    assert worker.pendientes_capac() == ["A"]


def test_procesar_capac_exito(tmp_path, monkeypatch):
    _bajada_sin_analisis(tmp_path, monkeypatch, "A")
    assert worker.procesar_capac("A", lambda cod: {"ok": True, "score_despues": 90}) is True


def test_procesar_capac_error_no_frena_y_traza(tmp_path, monkeypatch):
    _bajada_sin_analisis(tmp_path, monkeypatch, "A")

    def _boom(cod):
        raise RuntimeError("Claude timeout")

    assert worker.procesar_capac("A", _boom) is False
    with db.conn() as c:
        ev = c.execute("SELECT 1 FROM eventos WHERE codigo='A' AND tipo='error'").fetchone()
        fila = c.execute("SELECT 1 FROM analisis_bases WHERE codigo='A'").fetchone()
    assert ev is not None       # queda traza del error
    assert fila is None         # NO dejó fila -> pendientes_capac lo vuelve a tomar (reintento)


def test_una_pasada_encadena_baja_y_capac(tmp_path, monkeypatch):
    """End-to-end del loop: baja (mock) y analiza (mock) en la misma pasada, sin red ni tokens."""
    import schema_v3
    _setup(tmp_path, monkeypatch)
    schema_v3.migrate()
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "A", "nombre": "x"})
        db.set_admisibilidad(c, "A", True, "ok", True)

    def _baja(cod):  # simula download.descargar_codigo: deja las bases 'descargado'
        with db.conn() as c:
            c.execute("UPDATE licitaciones SET docs_estado='descargado' WHERE codigo=?", (cod,))
        return True

    capac_calls = []

    def _analiza(cod):
        capac_calls.append(cod)
        with db.conn() as c:  # simula el cacheo real en analisis_bases
            c.execute("INSERT INTO analisis_bases (codigo, ts) VALUES (?, ?)", (cod, "2026-07-08"))
        return {"ok": True, "score_despues": 88}

    r = worker.una_pasada(descargar=_baja, analizar=_analiza, con_capac=True)
    assert r == {"pendientes": 1, "procesadas": 1, "capac": 1}
    assert capac_calls == ["A"]  # la misma lic bajada se analizó en la pasada


def test_una_pasada_capac_apagado_no_analiza(tmp_path, monkeypatch):
    _bajada_sin_analisis(tmp_path, monkeypatch, "A")
    called = []
    r = worker.una_pasada(descargar=lambda cod: True,
                          analizar=lambda cod: called.append(cod), con_capac=False)
    assert r["capac"] == 0 and called == []
