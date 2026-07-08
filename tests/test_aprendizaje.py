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


# ---------------------------------------------------------------- Fase B: aprender de resultados (puro)
def test_victorias_suben_el_score_sobre_umbral_res():
    """Una racha de ganadas por comprador SUBE el score de parecidas (delta +)."""
    cargado = {"gana_org": {"Muni Z": aprendizaje.UMBRAL_RES}}
    a = aprendizaje.ajuste_lic(cargado, "Región", "Muni Z")
    assert a["delta"] == aprendizaje.BONUS["gana_org"]
    assert a["razones"] and a["razones"][0].startswith("+")


def test_victorias_por_region_suben():
    cargado = {"gana_region": {"Maule": aprendizaje.UMBRAL_RES}}
    a = aprendizaje.ajuste_lic(cargado, "Maule", "Cualquiera")
    assert a["delta"] == aprendizaje.BONUS["gana_region"]


def test_perdida_malfit_baja_el_score():
    """Pérdida estructural (mal fit) por comprador BAJA el score de parecidas."""
    cargado = {"malfit_org": {"Muni W": aprendizaje.UMBRAL_RES}}
    a = aprendizaje.ajuste_lic(cargado, "Región", "Muni W")
    assert a["delta"] == -aprendizaje.PENAL["malfit"]
    assert a["razones"] and "mal fit" in a["razones"][0].lower()


def test_perdida_competida_no_toca_el_score():
    """Regla de producto: perder por precio/competencia NO baja el fit (era buena)."""
    # 'competida' nunca entra a cargar() (se filtra por impacto), así que no hay clave que la represente.
    cargado = {"gana_org": {}, "malfit_org": {}, "gana_region": {}}
    a = aprendizaje.ajuste_lic(cargado, "Región", "Muni Competida")
    assert a["delta"] == 0
    assert not a["razones"]


def test_victoria_y_malfit_se_netean():
    """Ganás y perdés por mal fit al mismo comprador: los deltas se compensan (transparente)."""
    cargado = {"gana_org": {"Muni M": aprendizaje.UMBRAL_RES},
               "malfit_org": {"Muni M": aprendizaje.UMBRAL_RES}}
    a = aprendizaje.ajuste_lic(cargado, "Región", "Muni M")
    assert a["delta"] == aprendizaje.BONUS["gana_org"] - aprendizaje.PENAL["malfit"]
    assert len(a["razones"]) == 2


def test_cargar_lee_resultados_end_to_end(tmp_path, monkeypatch):
    """De marcar_resultado hasta el ajuste: victorias y malfit se agregan por eje."""
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v3.migrate()
    with db.conn() as c:
        for i in range(aprendizaje.UMBRAL_RES):
            db.upsert_licitacion(c, {"codigo": f"W{i}", "nombre": "x",
                                     "region": "Maule", "organismo": "Muni Gana"})
        for i in range(aprendizaje.UMBRAL_RES):
            db.upsert_licitacion(c, {"codigo": f"F{i}", "nombre": "x",
                                     "region": "Maule", "organismo": "Muni Malfit"})
        # una competida: no debe pesar en el score
        db.upsert_licitacion(c, {"codigo": "C0", "nombre": "x",
                                 "region": "Maule", "organismo": "Muni Comp"})
    for i in range(aprendizaje.UMBRAL_RES):
        feedback.marcar_resultado(f"W{i}", "ganada", categoria="precio_competitivo")
        feedback.marcar_resultado(f"F{i}", "perdida", categoria="requisito")
    feedback.marcar_resultado("C0", "perdida", categoria="competencia_fuerte")

    cargado = aprendizaje.cargar()
    assert cargado["gana_org"].get("Muni Gana") == aprendizaje.UMBRAL_RES
    assert cargado["malfit_org"].get("Muni Malfit") == aprendizaje.UMBRAL_RES
    assert "Muni Comp" not in cargado["malfit_org"]  # la competida no se agregó

    assert aprendizaje.ajuste_lic(cargado, "Maule", "Muni Gana")["delta"] > 0
    assert aprendizaje.ajuste_lic(cargado, "X", "Muni Malfit")["delta"] < 0
    assert aprendizaje.ajuste_lic(cargado, "X", "Muni Comp")["delta"] == 0
