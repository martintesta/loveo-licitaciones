"""
test_resultados.py — Sensor de la captura de resultado con motivo (Fase A, aprender-de-resultados).

feedback.marcar_resultado guarda el estado + la categoría con su impacto derivado
(positivo / malfit / competida / neutro), que la Fase B usará para aprender. SQLite temporal.

  python -m pytest tests/test_resultados.py -q
"""
import db
import feedback
import schema_v3


def _lic(monkeypatch, tmp_path, codigo):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v3.migrate()
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": codigo, "nombre": "Prueba"})


def _fila(codigo):
    with db.conn() as c:
        return c.execute("SELECT resultado, categoria, impacto FROM resultados WHERE codigo=?",
                         (codigo,)).fetchone()


def test_ganada_impacto_positivo(tmp_path, monkeypatch):
    _lic(monkeypatch, tmp_path, "G1")
    feedback.marcar_resultado("G1", "ganada", categoria="precio_competitivo")
    r = _fila("G1")
    assert r["resultado"] == "ganada"
    assert r["impacto"] == "positivo"
    with db.conn() as c:
        est = c.execute("SELECT estado_resultado FROM licitaciones WHERE codigo='G1'").fetchone()
    assert est["estado_resultado"] == "ganada"   # también movió el estado


def test_perdida_estructural_es_malfit(tmp_path, monkeypatch):
    _lic(monkeypatch, tmp_path, "P1")
    feedback.marcar_resultado("P1", "perdida", categoria="requisito")
    assert _fila("P1")["impacto"] == "malfit"    # baja el score de parecidas (Fase B)


def test_perdida_competitiva_no_baja_el_fit(tmp_path, monkeypatch):
    _lic(monkeypatch, tmp_path, "P2")
    feedback.marcar_resultado("P2", "perdida", categoria="competencia_fuerte")
    assert _fila("P2")["impacto"] == "competida"  # NO toca el score (era buena, competiste)


def test_sin_categoria_no_rompe(tmp_path, monkeypatch):
    _lic(monkeypatch, tmp_path, "P3")
    feedback.marcar_resultado("P3", "perdida")
    r = _fila("P3")
    assert r["categoria"] is None and r["impacto"] is None


def test_categorias_resultado_para_ui_tiene_ganada_y_perdida():
    cats = feedback.categorias_resultado_para_ui()
    resultados = {c["resultado"] for c in cats}
    assert resultados == {"ganada", "perdida"}
    impactos = {c["impacto"] for c in cats}
    assert {"positivo", "malfit", "competida"} <= impactos
