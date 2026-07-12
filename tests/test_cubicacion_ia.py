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


# ---------------------------------------------------------------- Fase 2: curación (guardar_borrador)
def test_guardar_reemplaza_el_borrador(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    cubicacion_ia.generar("A", extraer=_extraccion([{"descripcion": "auto1", "cantidad": 1, "unidad": "u"}]))
    # el usuario cura: cambia cantidad, saca uno, agrega otro
    r = cubicacion_ia.guardar_borrador("A", [
        {"descripcion": "auto1 corregido", "cantidad": "5", "unidad": "m2", "grupo": "material"},
        {"descripcion": "Flete", "cantidad": 1, "unidad": "gl", "grupo": "transporte"}])
    assert r["ok"] and len(r["items"]) == 2
    items = cubicacion_ia.borrador("A")
    assert [i["descripcion"] for i in items] == ["auto1 corregido", "Flete"]
    assert items[0]["cantidad"] == 5.0 and items[1]["grupo"] == "transporte"


def test_guardar_descarta_filas_sin_descripcion(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = cubicacion_ia.guardar_borrador("A", [
        {"descripcion": "válida", "cantidad": 2, "unidad": "u"},
        {"descripcion": "  ", "cantidad": 9, "unidad": "u"}])   # vacía → se descarta
    assert len(r["items"]) == 1 and r["items"][0]["descripcion"] == "válida"


def test_guardar_crea_si_no_existia(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)   # nunca se generó el borrador IA
    r = cubicacion_ia.guardar_borrador("A", [{"descripcion": "manual", "cantidad": 3, "unidad": "u"}])
    assert r["ok"] and cubicacion_ia.borrador("A")[0]["descripcion"] == "manual"


def test_cantidad_formato_chileno():
    assert cubicacion_ia._cantidad("1,5") == 1.5          # coma decimal (Chile)
    assert cubicacion_ia._cantidad("1.000,5") == 1000.5   # punto miles + coma decimal
    assert cubicacion_ia._cantidad("120") == 120.0
    assert cubicacion_ia._cantidad("1.5") == 1.5          # sin coma → punto decimal (inglés) ok
    assert cubicacion_ia._cantidad("") is None and cubicacion_ia._cantidad(None) is None
    assert cubicacion_ia._cantidad("abc") is None


def test_guardar_cantidad_con_coma_no_se_pierde(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = cubicacion_ia.guardar_borrador("A", [{"descripcion": "Acero", "cantidad": "12,5", "unidad": "kg"}])
    assert r["items"][0]["cantidad"] == 12.5             # antes se perdía (float('12,5') → error)


def test_guardar_respeta_valentina(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with db.conn() as c:
        c.execute("INSERT INTO cubicaciones (proyecto, codigo, origen, fecha) VALUES (?,?,?,?)",
                  ("A", "A", "valentina", "2026-07-01"))
    r = cubicacion_ia.guardar_borrador("A", [{"descripcion": "x", "cantidad": 1, "unidad": "u"}])
    assert r["ok"] is False and "Valentina" in r["error"]
