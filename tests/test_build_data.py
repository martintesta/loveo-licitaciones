"""
test_build_data.py — Smoke del único camino de lectura de la UI (tablero_data.build_data).

build_data() es lo que alimenta TODA la consola. Un import roto o un SQL que falla acá
tumba la app entera. Este smoke lo corre contra sqlite temporal vacío y verifica que
devuelve la estructura esperada sin crashear.

  python -m pytest tests/test_build_data.py -q
"""
import db


def test_build_data_devuelve_estructura(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    import tablero_data
    data = tablero_data.build_data()
    for k in ("lics", "order", "groups", "intel", "metricas", "keywords", "aprendizaje", "meta"):
        assert k in data, f"falta la key {k}"
    assert isinstance(data["lics"], dict)
    assert isinstance(data["order"], list)
    assert isinstance(data["groups"], dict)
    # el panel de aprendizaje siempre trae su umbral (aunque no haya descartes)
    assert "umbral" in data["aprendizaje"]
    assert "actualizado" in data  # freshness de los datos


def test_incompleto_marca_lics_sin_detalle(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "SINDET", "nombre": "solo codigo y nombre"})   # sin json_detalle
        db.upsert_licitacion(c, {"codigo": "CONDET", "nombre": "con detalle", "json_detalle": "{}"})
    import tablero_data
    data = tablero_data.build_data()
    assert data["lics"]["SINDET"]["incompleto"] is True   # extracción incompleta -> badge "SIN DETALLE"
    assert data["lics"]["CONDET"]["incompleto"] is False
    assert data["actualizado"]  # hay fecha de actualización


def test_build_data_no_repite_el_trabajo_pesado(tmp_path, monkeypatch):
    """Perf: migrate() está cacheado por base, así que el DDL (db.init_db) corre UNA sola vez
    pese a múltiples build_data y a que muchos módulos llaman migrate()."""
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    import schema_v3
    import tablero_data
    key = str(tmp_path / "t.db")
    schema_v3._MIGRATED.discard(key)
    tablero_data._INIT_DONE.discard(key)

    n = {"c": 0}
    orig = db.init_db
    monkeypatch.setattr(db, "init_db", lambda: (n.__setitem__("c", n["c"] + 1), orig())[1])

    tablero_data.build_data()
    tablero_data.build_data()
    assert n["c"] == 1   # el trabajo pesado del schema corre una sola vez por proceso/base
