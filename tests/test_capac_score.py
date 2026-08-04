"""
test_capac_score.py — Capa C aplicada al score (capac_score.analizar).

Cubre la coerción de campos que la IA a veces devuelve como dict/list/str donde se espera un
escalar (plazo/presupuesto) — antes reventaba al bindearlos a SQLite ("type 'dict' is not
supported", caso real 1216062-18-LR26). capa_c.analizar_bases mockeado → sin API ni PDFs.

  python -m pytest tests/test_capac_score.py -q
"""
import json

import capa_c
import capac_score
import db
import schema_v3


def test_num_coerce():
    assert capac_score._num(60) == 60
    assert capac_score._num("336.469.000") == 336469000     # formato CLP → dígitos
    assert capac_score._num("60 días") == 60
    assert capac_score._num({"min": 30}) is None            # dict → None (no revienta SQLite)
    assert capac_score._num([1, 2]) is None
    assert capac_score._num(None) is None
    assert capac_score._num("s/d") is None
    assert capac_score._num(True) is None                   # bool no es número acá


def test_texto_coerce():
    assert capac_score._texto("hola") == "hola"
    assert capac_score._texto(None) is None
    assert capac_score._texto({"a": 1}) == '{"a": 1}'       # dict → JSON para columna TEXT


def test_analizar_no_revienta_con_dict_en_plazo(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v3.migrate()
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "D", "nombre": "Módulos", "region": "Maule"})
        db.set_score_provisional(c, "D", 80, json.dumps({"dimensiones": {}}), True)

    # la IA devuelve dict donde se espera escalar (reproduce el bug real de 1216062-18-LR26)
    monkeypatch.setattr(capa_c, "analizar_bases", lambda codigo=None, **k: {
        "modelo": "test", "meta": [],
        "extraccion": {"presupuesto_clp": {"monto": 5000000},
                       "plazo_entrega_dias": {"min": 30, "max": 60},
                       "señales_complejidad": ["izaje"], "resumen": {"x": 1}}})
    r = capac_score.analizar("D")
    assert r["ok"] is True                                  # antes: EXC "type 'dict' is not supported"
    with db.conn() as c:
        row = c.execute("SELECT plazo_dias, presupuesto_clp, resumen FROM analisis_bases "
                        "WHERE codigo='D'").fetchone()
    assert row["plazo_dias"] is None and row["presupuesto_clp"] is None   # dicts → None
    assert isinstance(row["resumen"], str)                  # dict → JSON string


def _prep(tmp_path, monkeypatch, cod):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v3.migrate()
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": cod, "nombre": "Módulos", "region": "Maule"})
        db.set_score_provisional(c, cod, 80, json.dumps({"dimensiones": {}}), True)


_OK_EXTRACT = {"modelo": "t", "meta": [],
               "extraccion": {"presupuesto_clp": 5000000, "plazo_entrega_dias": 60,
                              "señales_complejidad": ["x"], "resumen": "ok"}}


def test_analizar_reintenta_ante_parse_error(tmp_path, monkeypatch):
    # 1er intento devuelve JSON inválido (intermitente); el 2do sale → analizar persiste OK
    _prep(tmp_path, monkeypatch, "R")
    llamadas = {"n": 0}

    def _flaky(codigo=None, **k):
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            return {"modelo": "t", "meta": [], "extraccion": {"_parse_error": True, "raw": "..."}}
        return _OK_EXTRACT

    monkeypatch.setattr(capa_c, "analizar_bases", _flaky)
    r = capac_score.analizar("R")
    assert r["ok"] is True and llamadas["n"] == 2           # reintentó una vez y salió


def test_analizar_falla_tras_dos_parse_errors(tmp_path, monkeypatch):
    _prep(tmp_path, monkeypatch, "R2")
    monkeypatch.setattr(capa_c, "analizar_bases",
                        lambda codigo=None, **k: {"extraccion": {"_parse_error": True}})
    r = capac_score.analizar("R2")
    assert r["ok"] is False and "2 intentos" in r["error"]
