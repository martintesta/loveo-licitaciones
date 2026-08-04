"""
test_cubicacion_ia.py — Sensor de la cubicación asistida (Fase 1, spec cubicacion-asistida).

generar() toma la extracción de la Capa C (materiales), la normaliza y la persiste como un borrador
cubicaciones(origen='ia') + cubicacion_items. Extractor INYECTADO → no gasta tokens. SQLite temporal.

  python -m pytest tests/test_cubicacion_ia.py -q
"""
import json

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
    assert cubicacion_ia._cantidad("1.5") == 1.5          # 1 decimal → decimal (1,5 m²)
    assert cubicacion_ia._cantidad("2.75") == 2.75        # 2 decimales → decimal (2,75 ton)
    assert cubicacion_ia._cantidad("") is None and cubicacion_ia._cantidad(None) is None
    assert cubicacion_ia._cantidad("abc") is None


def test_cantidad_miles_chilenos_no_se_achica():
    """Regresión: '1.000' daba 1.0 → costo ~1000× bajo → MARGEN INFLADO (auditoría)."""
    assert cubicacion_ia._cantidad("1.000") == 1000.0
    assert cubicacion_ia._cantidad("2.500") == 2500.0
    assert cubicacion_ia._cantidad("1.234.567") == 1234567.0
    assert cubicacion_ia._cantidad("120 un") == 120.0     # limpia la unidad pegada
    assert cubicacion_ia._cantidad(1500) == 1500.0        # numérico pasa derecho
    assert cubicacion_ia._cantidad(True) is None          # bool no es cantidad


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


# ---------------------------------------------------------------- Fase 4: margen real → score
def _techo(codigo, presupuesto):
    with db.conn() as c:
        c.execute("INSERT INTO analisis_bases (codigo, ts, presupuesto_clp) VALUES (?,?,?)",
                  (codigo, "2026-07-10", presupuesto))


def _preciar_todo(codigo, precio):
    cubicacion_ia.preciar(codigo, buscar=lambda d, u: {"precio": precio, "url": "https://x.cl/p"})


def test_score_margen_por_tramos():
    assert cubicacion_ia._score_margen(35) == 9
    assert cubicacion_ia._score_margen(22) == 7
    assert cubicacion_ia._score_margen(12) == 5
    assert cubicacion_ia._score_margen(3) == 3
    assert cubicacion_ia._score_margen(-10) == 1


def test_margen_aplica_al_score_si_todo_preciado(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _borrador("A", [{"descripcion": "Panel", "cantidad": 10, "unidad": "m2"}])
    _preciar_todo("A", 30000)          # costo = 10 × 30.000 = 300.000
    _techo("A", 500000)                # techo 500.000 → margen 40% → score 9
    r = cubicacion_ia.margen("A")
    assert r["ok"] and r["aplicado"] is True
    assert r["costo"] == 300000 and r["techo"] == 500000
    assert r["margen"] == 200000 and r["margen_pct"] == 40.0
    # la dimensión margen del score quedó evaluada (9/10)
    with db.conn() as c:
        sj = json.loads(c.execute("SELECT score_json FROM licitaciones WHERE codigo='A'").fetchone()["score_json"])
    assert sj["dimensiones"]["margen"]["evaluado"] is True
    assert sj["dimensiones"]["margen"]["score"] == 9


def test_margen_parcial_no_toca_el_score(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _borrador("A", [{"descripcion": "A", "cantidad": 1, "unidad": "u"},
                    {"descripcion": "B", "cantidad": 1, "unidad": "u"}])
    # preciar solo uno: web devuelve precio para 'A' y None para 'B'
    cubicacion_ia.preciar("A", buscar=lambda d, u: {"precio": 1000, "url": "https://x.cl"} if d == "A" else None)
    _techo("A", 100000)
    r = cubicacion_ia.margen("A")
    assert r["ok"] and r["aplicado"] is False and r["sin_precio"] == 1
    with db.conn() as c:   # el score NO se tocó (no hay score_json de margen evaluado)
        row = c.execute("SELECT score_json FROM licitaciones WHERE codigo='A'").fetchone()
    assert row["score_json"] is None or "margen" not in (json.loads(row["score_json"]).get("dimensiones", {}))


def test_margen_sin_techo_falla(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _borrador("A", [{"descripcion": "X", "cantidad": 1, "unidad": "u"}])
    _preciar_todo("A", 1000)           # preciado, pero sin techo de presupuesto
    r = cubicacion_ia.margen("A")
    assert r["ok"] is False and "presupuesto" in r["error"].lower()


def test_margen_sin_cubicacion_falla(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert cubicacion_ia.margen("A")["ok"] is False


def test_margen_no_aplica_si_una_partida_no_tiene_cantidad(tmp_path, monkeypatch):
    """Gate de honestidad: una partida CON precio pero SIN cantidad (total=None) NO debe dejar
    aplicar el margen al score — su costo quedaría en $0 y subestimaría el total."""
    _setup(tmp_path, monkeypatch)
    _borrador("A", [{"descripcion": "Panel", "cantidad": 10, "unidad": "m2"},
                    {"descripcion": "Estructura acero", "cantidad": None, "unidad": "kg"}])
    cubicacion_ia.preciar("A", buscar=lambda d, u: {
        "precio": 30000 if "Panel" in d else 4000000, "url": "https://x.cl"})
    _techo("A", 500000)
    r = cubicacion_ia.margen("A")
    assert r["ok"] and r["aplicado"] is False and r["sin_precio"] == 1
    with db.conn() as c:   # el score NO se tocó (margen no evaluado)
        row = c.execute("SELECT score_json FROM licitaciones WHERE codigo='A'").fetchone()
    dims = (json.loads(row["score_json"]).get("dimensiones", {}) if row["score_json"] else {})
    assert not dims.get("margen", {}).get("evaluado")


# ---------------------------------------------------------------- Fase 5: recetas por tipo de producto
def test_tipo_producto_clasifica():
    assert cubicacion_ia.tipo_producto("Provisión de container 20 pies") == "contenedor"
    assert cubicacion_ia.tipo_producto("Sala modular para escuela") == "modular"
    assert cubicacion_ia.tipo_producto("Baños químicos") == "bano"
    assert cubicacion_ia.tipo_producto("Servicio de aseo") is None


def _lic2(codigo, nombre):
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": codigo, "nombre": nombre})


def test_curar_alimenta_la_receta_del_tipo(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)   # 'A' se llama "Módulos" → tipo modular
    r = cubicacion_ia.guardar_borrador("A", [{"descripcion": "Panel", "cantidad": 20, "unidad": "m2"}])
    assert r["receta_tipo"] == "modular"
    # la receta 'modular' quedó guardada (cubicaciones origen='receta')
    with db.conn() as c:
        rec = c.execute("SELECT id FROM cubicaciones WHERE proyecto='modular' AND origen='receta'").fetchone()
        n = c.execute("SELECT COUNT(*) n FROM cubicacion_items WHERE cubicacion_id=?", (rec["id"],)).fetchone()["n"]
    assert rec is not None and n == 1


def test_prellenar_desde_receta_en_lic_parecida(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    # curar 'A' (modular) crea la receta
    cubicacion_ia.guardar_borrador("A", [{"descripcion": "Panel SIP", "cantidad": 30, "unidad": "m2"},
                                         {"descripcion": "Estructura", "cantidad": 100, "unidad": "kg"}])
    # una lic NUEVA del mismo tipo (modular) pre-llena desde la receta, sin IA
    _lic2("B", "Oficina modular municipal")
    r = cubicacion_ia.prellenar_desde_receta("B")
    assert r["ok"] and r["tipo"] == "modular"
    items = cubicacion_ia.borrador("B")
    assert [i["descripcion"] for i in items] == ["Panel SIP", "Estructura"]
    assert items[0]["cantidad"] == 30


def test_prellenar_sin_receta_avisa(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _lic2("C", "Sala modular sin receta previa")
    r = cubicacion_ia.prellenar_desde_receta("C")
    assert r["ok"] is False and "receta" in r["error"].lower()


def test_prellenar_tipo_desconocido_avisa(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _lic2("D", "Servicio de vigilancia")   # no matchea ningún tipo
    r = cubicacion_ia.prellenar_desde_receta("D")
    assert r["ok"] is False and "tipo" in r["error"].lower()


def test_prellenar_respeta_valentina(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    cubicacion_ia.guardar_borrador("A", [{"descripcion": "x", "cantidad": 1, "unidad": "u"}])
    _lic2("B", "Módulos oficina")
    with db.conn() as c:
        c.execute("INSERT INTO cubicaciones (proyecto, codigo, origen, fecha) VALUES (?,?,?,?)",
                  ("B", "B", "valentina", "2026-07-01"))
    r = cubicacion_ia.prellenar_desde_receta("B")
    assert r["ok"] is False and "Valentina" in r["error"]


def test_build_data_expone_receta_disponible(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    cubicacion_ia.guardar_borrador("A", [{"descripcion": "Panel", "cantidad": 20, "unidad": "m2"}])
    _lic2("B", "Sala modular nueva")   # mismo tipo, sin cubicación propia
    import tablero_data
    lics = tablero_data.build_data()["lics"]
    assert lics["B"]["recetaDisp"] == {"tipo": "modular", "n": 1}


# ---------------------------------------------------------------- Fase 4 (plan-del-dia): receta = consenso
def test_receta_es_consenso_no_ultima_gana(tmp_path, monkeypatch):
    """La receta AGREGA todas las curaciones del tipo (mediana + consenso), no 'última gana':
    Panel está en las 3 → mediana; Estructura en 2/3 → entra; 'Flete raro' en 1/3 → se descarta."""
    _setup(tmp_path, monkeypatch)              # A = "Módulos" (modular)
    _lic2("B", "Oficina modular")
    _lic2("C", "Sala modular")
    cubicacion_ia.guardar_borrador("A", [{"descripcion": "Panel", "cantidad": 20, "unidad": "m2"},
                                         {"descripcion": "Estructura", "cantidad": 100, "unidad": "kg"}])
    cubicacion_ia.guardar_borrador("B", [{"descripcion": "Panel", "cantidad": 30, "unidad": "m2"},
                                         {"descripcion": "Flete raro", "cantidad": 1, "unidad": "gl"}])
    cubicacion_ia.guardar_borrador("C", [{"descripcion": "Panel", "cantidad": 40, "unidad": "m2"},
                                         {"descripcion": "Estructura", "cantidad": 120, "unidad": "kg"}])
    with db.conn() as c:
        rec = c.execute("SELECT id FROM cubicaciones WHERE proyecto='modular' AND origen='receta'").fetchone()
        items = {r["descripcion"]: r["cantidad"] for r in c.execute(
            "SELECT descripcion, cantidad FROM cubicacion_items WHERE cubicacion_id=?", (rec["id"],)).fetchall()}
    assert set(items) == {"Panel", "Estructura"}       # 'Flete raro' (1/3) quedó afuera
    assert items["Panel"] == 30                          # mediana(20,30,40), no la última (40)
    assert items["Estructura"] == 110                    # mediana(100,120)


def test_receta_ignora_borradores_no_curados(tmp_path, monkeypatch):
    """Solo la curación del usuario alimenta la receta: un borrador IA CRUDO (nunca curado) del mismo
    tipo no debe contaminar el consenso."""
    _setup(tmp_path, monkeypatch)              # A = modular
    _lic2("B", "Sala modular")
    cubicacion_ia.generar("B", extraer=_extraccion(   # B: borrador IA crudo, jamás curado
        [{"descripcion": "Basura cruda", "cantidad": 999, "unidad": "u"}]))
    cubicacion_ia.guardar_borrador("A", [{"descripcion": "Panel", "cantidad": 20, "unidad": "m2"}])
    with db.conn() as c:
        rec = c.execute("SELECT id FROM cubicaciones WHERE proyecto='modular' AND origen='receta'").fetchone()
        descs = {r["descripcion"] for r in c.execute(
            "SELECT descripcion FROM cubicacion_items WHERE cubicacion_id=?", (rec["id"],)).fetchall()}
    assert descs == {"Panel"}                  # 'Basura cruda' (borrador no curado) no entró
