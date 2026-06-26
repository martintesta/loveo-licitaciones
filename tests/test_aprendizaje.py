"""
test_aprendizaje.py — Sensor del descarte estructurado (Fase 2, spec curaduria-aprendizaje).

Verifica que feedback.descartar guarda la categoría y deriva bien el tipo
(calidad vs operativo) en la tabla `descartes`. Contra SQLite temporal (no toca Neon).

  python -m pytest tests/test_aprendizaje.py -q
"""
import db
import feedback
import schema_v3


def _lic(monkeypatch, tmp_path, codigo):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v3.migrate()  # crea la tabla `descartes` (la app la corre vía build_data)
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": codigo, "nombre": "Prueba"})


def _descarte(codigo):
    with db.conn() as c:
        return c.execute("SELECT categoria, tipo FROM descartes WHERE codigo=?", (codigo,)).fetchone()


def test_categoria_calidad_se_guarda_como_calidad(tmp_path, monkeypatch):
    _lic(monkeypatch, tmp_path, "D-CAL")
    feedback.descartar("D-CAL", "muy lejos de Pirque", categoria="muy_lejos")
    r = _descarte("D-CAL")
    assert r["categoria"] == "muy_lejos"
    assert r["tipo"] == "calidad"  # alimenta el ajuste de score (Fase 3)


def test_visita_perdida_es_operativo_no_calidad(tmp_path, monkeypatch):
    """Regla dura: un descarte operativo NUNCA debe contar como señal de calidad."""
    _lic(monkeypatch, tmp_path, "D-OP")
    feedback.descartar("D-OP", "no llegamos a la visita obligatoria", categoria="visita_perdida")
    r = _descarte("D-OP")
    assert r["tipo"] == "operativo"


def test_sin_categoria_no_rompe(tmp_path, monkeypatch):
    _lic(monkeypatch, tmp_path, "D-NONE")
    feedback.descartar("D-NONE", "sin categoría")
    r = _descarte("D-NONE")
    assert r["categoria"] is None
    assert r["tipo"] is None


def test_categorias_para_ui_tiene_los_dos_tipos():
    cats = feedback.categorias_para_ui()
    tipos = {c["tipo"] for c in cats}
    assert tipos == {"calidad", "operativo"}
    assert any(c["k"] == "visita_perdida" and c["tipo"] == "operativo" for c in cats)
