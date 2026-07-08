"""
test_comprador.py — Sensor de la reputación de pago por comprador (señal Ficha Comprador manual).

Verifica el upsert por organismo, la validación de nivel, la alerta para 'mala' y que build_data
adjunta repPago + suma la alerta al ajuste (sin tocar el score numérico). SQLite temporal.

  python -m pytest tests/test_comprador.py -q
"""
import pytest

import comprador
import db
import schema_v3


def _db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v3.migrate()


def test_set_y_leer_reputacion(tmp_path, monkeypatch):
    _db(monkeypatch, tmp_path)
    comprador.set_reputacion("Muni X", "mala", "paga a 90+ días")
    reps = comprador.reputaciones()
    assert reps["Muni X"]["nivel"] == "mala"
    assert reps["Muni X"]["nota"] == "paga a 90+ días"
    assert reps["Muni X"]["fuente"] == "manual"


def test_upsert_no_duplica(tmp_path, monkeypatch):
    _db(monkeypatch, tmp_path)
    comprador.set_reputacion("Muni X", "regular")
    comprador.set_reputacion("Muni X", "mala", "empeoró")   # mismo organismo -> actualiza
    reps = comprador.reputaciones()
    assert len(reps) == 1 and reps["Muni X"]["nivel"] == "mala" and reps["Muni X"]["nota"] == "empeoró"


def test_nivel_invalido_falla(tmp_path, monkeypatch):
    _db(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        comprador.set_reputacion("Muni X", "pesimo")


def test_organismo_vacio_falla(tmp_path, monkeypatch):
    _db(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        comprador.set_reputacion("  ", "mala")


def test_alerta_solo_para_mala():
    assert comprador.alerta_para({"nivel": "mala", "nota": "atrasos"}) is not None
    assert "atrasos" in comprador.alerta_para({"nivel": "mala", "nota": "atrasos"})
    assert comprador.alerta_para({"nivel": "buena", "nota": ""}) is None
    assert comprador.alerta_para({"nivel": "regular", "nota": ""}) is None
    assert comprador.alerta_para(None) is None


def test_build_data_adjunta_reputacion_y_alerta(tmp_path, monkeypatch):
    _db(monkeypatch, tmp_path)
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "L1", "nombre": "x", "organismo": "Muni Mala"})
        db.upsert_licitacion(c, {"codigo": "L2", "nombre": "y", "organismo": "Muni Ok"})
    comprador.set_reputacion("Muni Mala", "mala", "atrasos crónicos")
    comprador.set_reputacion("Muni Ok", "buena")
    import tablero_data
    lics = tablero_data.build_data()["lics"]
    assert lics["L1"]["repPago"]["nivel"] == "mala"
    assert lics["L2"]["repPago"]["nivel"] == "buena"
    # la reputación mala aparece como alerta del ajuste (heads-up), no como delta numérico
    assert any("MAL PAGADOR" in a for a in lics["L1"]["ajuste"]["alertas"])
    assert lics["L1"]["ajuste"]["delta"] == lics["L2"]["ajuste"]["delta"]  # el score no se movió
