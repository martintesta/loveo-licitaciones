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


# ---------------------------------------------------------------- Fase 3: precios (preciar)
def test_precio_num_formato_clp():
    assert cubicacion_ia._precio_num("$1.234.567") == 1234567.0   # punto = miles
    assert cubicacion_ia._precio_num("12.500") == 12500.0
    assert cubicacion_ia._precio_num("1.234,50") == 1234.5        # coma decimal
    assert cubicacion_ia._precio_num("125.50") == 125.5           # un punto + 2 decimales = decimal
    assert cubicacion_ia._precio_num("8.990") == 8990.0           # un punto + 3 dígitos = miles
    assert cubicacion_ia._precio_num(8990) == 8990.0
    assert cubicacion_ia._precio_num("s/d") is None


def _borrador(codigo, mats):
    cubicacion_ia.guardar_borrador(codigo, mats)


def test_preciar_usa_catalogo_interno(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    import cubicacion
    _borrador("A", [{"descripcion": "Perfil acero 100", "cantidad": 10, "unidad": "ml"}])
    with db.conn() as c:   # sembrar el catálogo interno
        c.execute("INSERT INTO precios_referencia (descripcion, descripcion_norm, unidad, "
                  "precio_unitario, fuente, fecha) VALUES (?,?,?,?,?,?)",
                  ("Perfil acero 100", cubicacion._na("Perfil acero 100"), "ml", 5000, "valentina", "2026-01-01"))
    # buscar web que NO debe llamarse (hay match interno)
    llamado = []
    r = cubicacion_ia.preciar("A", buscar=lambda d, u: llamado.append(d))
    assert r["ok"] and r["preciados"] == 1 and r["web"] == 0
    assert r["costo"] == 50000.0 and not llamado   # 10 × 5000
    it = cubicacion_ia.borrador("A")[0]
    assert it["precio_unitario"] == 5000 and it["precio_fuente"] == "interno" and it["total"] == 50000


def test_preciar_busca_web_para_huecos_y_cachea(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _borrador("A", [{"descripcion": "Panel SIP 100mm", "cantidad": 4, "unidad": "m2"}])
    r = cubicacion_ia.preciar("A", buscar=lambda d, u: {"precio": "$25.000", "url": "https://sodimac.cl/p/123"})
    assert r["ok"] and r["preciados"] == 1 and r["web"] == 1
    it = cubicacion_ia.borrador("A")[0]
    assert it["precio_unitario"] == 25000 and it["precio_fuente"] == "web"
    assert it["precio_url"] == "https://sodimac.cl/p/123" and it["total"] == 100000
    # se cacheó en el catálogo propio (fuente web + source_url) para la próxima
    with db.conn() as c:
        row = c.execute("SELECT precio_unitario, source_url FROM precios_referencia WHERE fuente='web'").fetchone()
    assert row["precio_unitario"] == 25000 and row["source_url"] == "https://sodimac.cl/p/123"


def test_preciar_web_apagado_deja_sin_precio(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _borrador("A", [{"descripcion": "Item raro", "cantidad": 1, "unidad": "u"}])
    llamado = []
    r = cubicacion_ia.preciar("A", buscar=lambda d, u: llamado.append(d), web=False)
    assert r["preciados"] == 0 and r["sin_precio"] == 1 and not llamado


def test_preciar_sin_borrador(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = cubicacion_ia.preciar("A", buscar=lambda d, u: None)
    assert r["ok"] is False
