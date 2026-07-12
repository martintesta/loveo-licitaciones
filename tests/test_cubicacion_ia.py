"""
test_cubicacion_ia.py — Sensor de la cubicación asistida (Fase 1, spec cubicacion-asistida).

generar() toma la extracción de la Capa C (materiales), la normaliza y la persiste como un borrador
cubicaciones(origen='ia') + cubicacion_items. Extractor INYECTADO → no gasta tokens. SQLite temporal.

  python -m pytest tests/test_cubicacion_ia.py -q
"""
import db
import cubicacion_ia
import schema_v3


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v3.migrate()
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "A", "nombre": "Módulos"})


def _extraccion(materiales):
    return lambda cod: {"extraccion": {"materiales": materiales}}


def test_generar_persiste_el_borrador(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    mats = [{"partida": "Estructura", "grupo": "material", "descripcion": "Perfil acero 100x100",
             "cantidad": 120, "unidad": "ml"},
            {"grupo": "mano_obra", "descripcion": "Montaje", "cantidad": None, "unidad": "gl"}]
    r = cubicacion_ia.generar("A", extraer=_extraccion(mats))
    assert r["ok"] and len(r["items"]) == 2
    items = cubicacion_ia.borrador("A")
    assert items[0]["descripcion"] == "Perfil acero 100x100"
    assert items[0]["cantidad"] == 120 and items[0]["unidad"] == "ml"
    assert items[1]["grupo"] == "mano_obra" and items[1]["cantidad"] is None


def test_grupo_invalido_cae_a_material(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = cubicacion_ia.generar("A", extraer=_extraccion(
        [{"descripcion": "Panel", "grupo": "cualquier_cosa", "cantidad": "5", "unidad": "m2"}]))
    assert r["ok"]
    it = cubicacion_ia.borrador("A")[0]
    assert it["grupo"] == "material" and it["cantidad"] == 5.0   # "5" string → float


def test_idempotente_regenerar_reemplaza(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    cubicacion_ia.generar("A", extraer=_extraccion([{"descripcion": "V1", "cantidad": 1, "unidad": "u"}]))
    cubicacion_ia.generar("A", extraer=_extraccion([{"descripcion": "V2", "cantidad": 2, "unidad": "u"},
                                                    {"descripcion": "V3", "cantidad": 3, "unidad": "u"}]))
    items = cubicacion_ia.borrador("A")
    assert [i["descripcion"] for i in items] == ["V2", "V3"]   # reemplazó, no acumuló


def test_no_pisa_la_cubicacion_de_valentina(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with db.conn() as c:
        c.execute("INSERT INTO cubicaciones (proyecto, codigo, origen, fecha) VALUES (?,?,?,?)",
                  ("A", "A", "valentina", "2026-07-01"))
    r = cubicacion_ia.generar("A", extraer=_extraccion([{"descripcion": "x", "cantidad": 1, "unidad": "u"}]))
    assert r["ok"] is False and "Valentina" in r["error"]
    assert cubicacion_ia.borrador("A") == []   # no generó nada


def test_sin_materiales_devuelve_error(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = cubicacion_ia.generar("A", extraer=_extraccion([]))
    assert r["ok"] is False and "no extrajo" in r["error"].lower()


def test_error_de_extraccion_se_propaga(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = cubicacion_ia.generar("A", extraer=lambda cod: {"error": "bases no descargadas"})
    assert r["ok"] is False and r["error"] == "bases no descargadas"


def test_build_data_expone_cubicIA(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    cubicacion_ia.generar("A", extraer=_extraccion(
        [{"descripcion": "Panel SIP", "grupo": "material", "cantidad": 40, "unidad": "m2"}]))
    import tablero_data
    lic = tablero_data.build_data()["lics"]["A"]
    assert lic["cubicIA"] and lic["cubicIA"][0]["descripcion"] == "Panel SIP"
