"""
test_aprendizaje.py — Sensor del descarte estructurado (Fase 2, spec curaduria-aprendizaje).

Verifica que feedback.descartar guarda la categoría y deriva bien el tipo
(calidad vs operativo) en la tabla `descartes`. Contra SQLite temporal (no toca Neon).

  python -m pytest tests/test_aprendizaje.py -q
"""
import aprendizaje
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


# ---------------------------------------------------------------- Fase 3: ajuste asistido (puro)
def test_ajuste_muy_lejos_penaliza_sobre_umbral():
    cargado = {"muy_lejos_region": {"Aysén": aprendizaje.UMBRAL}, "mal_pagador_org": {}, "visita_org": {}}
    a = aprendizaje.ajuste_lic(cargado, "Aysén", "Comprador X")
    assert a["delta"] == -aprendizaje.PENAL["muy_lejos"]
    assert a["razones"] and "Aysén" in a["razones"][0]


def test_ajuste_bajo_umbral_no_penaliza():
    cargado = {"muy_lejos_region": {"Aysén": aprendizaje.UMBRAL - 1}, "mal_pagador_org": {}, "visita_org": {}}
    a = aprendizaje.ajuste_lic(cargado, "Aysén", "Comprador X")
    assert a["delta"] == 0
    assert not a["razones"]


def test_visita_perdida_no_penaliza_solo_alerta():
    """Regla dura: un descarte operativo NUNCA baja el score; solo alerta."""
    cargado = {"muy_lejos_region": {}, "mal_pagador_org": {}, "visita_org": {"Muni Y": 2}}
    a = aprendizaje.ajuste_lic(cargado, "Región", "Muni Y")
    assert a["delta"] == 0
    assert a["alertas"] and "visita" in a["alertas"][0].lower()


def test_requisito_excluyente_penaliza_por_comprador():
    """#9: nueva señal atribuible — si un comprador siempre exige lo que no podés."""
    cargado = {"requisito_excluyente_org": {"Muni W": aprendizaje.UMBRAL}}
    a = aprendizaje.ajuste_lic(cargado, "Región", "Muni W")
    assert a["delta"] == -aprendizaje.PENAL["requisito_excluyente"]
    assert a["razones"] and "requisito" in a["razones"][0].lower()


def test_penales_se_acumulan_mismo_comprador():
    """Dos patrones de calidad sobre el mismo comprador suman su penalización."""
    cargado = {"mal_pagador_org": {"Muni W": aprendizaje.UMBRAL},
               "requisito_excluyente_org": {"Muni W": aprendizaje.UMBRAL}}
    a = aprendizaje.ajuste_lic(cargado, "X", "Muni W")
    assert a["delta"] == -(aprendizaje.PENAL["mal_pagador"] + aprendizaje.PENAL["requisito_excluyente"])
    assert len(a["razones"]) == 2


# ---------------------------------------------------------------- Fase 3: carga desde DB (integración)
def test_cargar_y_ajuste_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v3.migrate()
    with db.conn() as c:
        for i in range(aprendizaje.UMBRAL):
            db.upsert_licitacion(c, {"codigo": f"L{i}", "nombre": "x",
                                     "region": "Aysén", "organismo": "Muni Z"})
    for i in range(aprendizaje.UMBRAL):
        feedback.descartar(f"L{i}", "muy lejos", categoria="muy_lejos")

    cargado = aprendizaje.cargar()
    assert cargado["muy_lejos_region"].get("Aysén") == aprendizaje.UMBRAL
    a = aprendizaje.ajuste_lic(cargado, "Aysén", "Muni Z")
    assert a["delta"] < 0  # el patrón real movió el score

    res = aprendizaje.resumen(cargado)
    assert any(p["categoria"] == "muy_lejos" for p in res["por_categoria"])
