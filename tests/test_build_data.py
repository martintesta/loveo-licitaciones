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
