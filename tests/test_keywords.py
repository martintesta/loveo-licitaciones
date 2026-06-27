"""
test_keywords.py — Sensor del parser de comandos /kw y del alta/listado.

No toca la IA (evaluar): cubre el ruteo de comando() + add/get_active_lists contra sqlite temporal.

  python -m pytest tests/test_keywords.py -q
"""
import db
import schema_v3
import keywords


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v3.migrate()


def test_comando_help(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert isinstance(keywords.comando("/kw help"), str)
    assert isinstance(keywords.comando("/kw"), str)  # sin subcomando -> ayuda


def test_comando_list(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert "incluir" in keywords.comando("/kw list").lower()


def test_comando_add_incluir_agrega(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    out = keywords.comando("/kw add-incluir contenedor refrigerado")
    assert "contenedor refrigerado" in out
    inc, _exc, _amp = keywords.get_active_lists()
    assert "contenedor refrigerado" in inc


def test_comando_desconocido(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert "no reconocido" in keywords.comando("/kw zzz").lower()


def test_add_y_set_activo(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    keywords.add("panel solar", "incluir", origen="manual")
    assert "panel solar" in keywords.get_active_lists()[0]
    fila = next(k for k in keywords.listar(tipo="incluir") if k["termino"] == "panel solar")
    keywords.set_activo(fila["id"], False)
    assert "panel solar" not in keywords.get_active_lists()[0]
