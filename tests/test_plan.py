"""
test_plan.py — Sensor del motor "Plan del día" / próxima mejor acción (epic plan-del-dia, Fase 1).

plan.construir compone las señales del `lics` de build_data en una cola priorizada de acciones.
Puro (dicts → acciones), sin DB.

  python -m pytest tests/test_plan.py -q
"""
import plan


def _lic(cod, **kw):
    base = {"cod": cod, "nom": "Lic " + cod, "org": "Muni X", "regc": "Maule",
            "estRev": "nueva", "estRes": None, "score": 80, "evDims": 6, "nDims": 6,
            "tri": "Priorizar", "dias": None, "diasVisita": None, "analisis": None, "dims": []}
    base.update(kw)
    return base


def _plan(*lics, **kw):
    return plan.construir({l["cod"]: l for l in lics}, **kw)


def test_visita_proxima_manda_sobre_una_nueva_lejana():
    # A: visita mañana (crítica). B: nueva fit sin deadline. A debe ir primero y ser tipo VISITA.
    a = _lic("A", diasVisita=1, estRev="aprobada", score=70)
    b = _lic("B", tri="Priorizar", score=95)
    res = _plan(a, b)
    assert res[0]["codigo"] == "A" and res[0]["tipo"] == "VISITA"
    assert "mañana" in res[0]["motivo"]


def test_accion_segun_estado_al_cerrar_pronto():
    aprob = _lic("AP", estRev="aprobada", dias=3)
    conbases = _lic("CB", estRev="en_revision", dias=3, analisis={"ts": "x"},
                    dims=[{"n": "Margen", "ev": False}])
    nueva = _lic("NU", estRev="nueva", dias=3)
    tipos = {a["codigo"]: a["tipo"] for a in _plan(aprob, conbases, nueva)}
    assert tipos == {"AP": "PRESENTAR", "CB": "CUBICAR", "NU": "REVISAR"}


def test_nueva_fit_sin_deadline_es_revisar_de_menor_prioridad():
    urgente = _lic("U", dias=2, estRev="nueva", score=60)          # cierra en 2
    tranqui = _lic("T", tri="Priorizar", score=95)                 # nueva valiosa, sin deadline
    res = _plan(urgente, tranqui)
    assert res[0]["codigo"] == "U"                                 # el deadline manda sobre el valor
    assert {a["tipo"] for a in res} == {"REVISAR"}


def test_cubicar_pendiente_sin_deadline():
    l = _lic("C", estRev="aprobada", analisis={"ts": "x"}, dims=[{"n": "Margen", "ev": False}])
    res = _plan(l)
    assert res and res[0]["tipo"] == "CUBICAR"


def test_excluye_descartadas_y_presentadas():
    d = _lic("D", estRev="descartada", dias=1)
    p = _lic("P", estRes="presentada", dias=1)
    g = _lic("G", estRes="ganada")
    assert _plan(d, p, g) == []


def test_sin_accion_si_nada_pendiente():
    # aprobada, sin deadline, con margen ya hecho → no hay nada que sugerir
    l = _lic("X", estRev="aprobada", tri="Priorizar", analisis={"ts": "x"},
             dims=[{"n": "Margen", "ev": True}])
    assert _plan(l) == []


def test_prioridad_pondera_valor_y_confianza():
    # dos visitas mismo día: la de mayor score×confianza va primero
    alto = _lic("H", diasVisita=2, score=100, evDims=6, nDims=6)
    bajo = _lic("L", diasVisita=2, score=100, evDims=3, nDims=6)   # misma nota, mitad de confianza
    res = _plan(alto, bajo)
    assert [a["codigo"] for a in res] == ["H", "L"]


def test_bases_para_seguida_sin_analizar():
    # la seguís (en_revision, score bueno) pero sin bases → acción BASES (conseguí las bases)
    l = _lic("B", estRev="en_revision", tri="Priorizar", analisis=None)
    res = _plan(l)
    assert res and res[0]["tipo"] == "BASES" and "bases" in res[0]["motivo"].lower()


def test_excluye_cierre_ya_pasado():
    l = _lic("V", estRev="nueva", tri="Priorizar", dias=-2)   # ya cerró
    assert _plan(l) == []


def test_visita_ya_pasada_no_es_accionable():
    # diasVisita negativo (la hora ya pasó, lo marca build_data) → no genera VISITA
    l = _lic("P", estRev="aprobada", diasVisita=-1, dias=20)
    res = _plan(l)
    assert not any(a["tipo"] == "VISITA" for a in res)


def test_limite():
    lics = [_lic(f"C{i}", dias=1) for i in range(20)]
    assert len(_plan(*lics, limite=5)) == 5


# ---------------------------------------------------------------- Fase 3: aprender del comportamiento
def test_es_engagement():
    assert plan.es_engagement("aprobar") and plan.es_engagement("cubic_margen")
    assert plan.es_engagement("resultado:ganada")
    assert not plan.es_engagement("descartar") and not plan.es_engagement("kw_add")


def test_no_es_engagement_calificar_pago_ni_preview():
    """Auditoría: rep_pago puede marcar un comprador como MALO — contarlo como preferencia hacía
    que el plan priorizara al comprador que se quiere evitar. capac es solo el preview de costo."""
    assert not plan.es_engagement("rep_pago")
    assert not plan.es_engagement("capac")
    assert plan.es_engagement("capac_run")          # el análisis REAL sí cuenta


def test_preferencia_sube_lo_que_el_usuario_ataca():
    # dos acciones REVISAR mismo valor; la preferencia por el comprador de A la sube
    a = _lic("A", tri="Priorizar", org="Muni Fav", reg="Maule", tipoProd="modular")
    b = _lic("B", tri="Priorizar", org="Muni Otra", reg="Ñuble", tipoProd="bano")
    sin = _plan(a, b)
    prefs = {"organismo": {"Muni Fav": 25.0}, "region": {"Maule": 10.0}, "tipo": {}}
    con = plan.construir({"A": a, "B": b}, prefs=prefs)
    assert {x["codigo"] for x in sin} == {"A", "B"}
    assert con[0]["codigo"] == "A"                    # la preferencia la puso primera
    assert con[0]["prioridad"] > sin[0 if sin[0]["codigo"] == "A" else 1]["prioridad"]


def test_registrar_y_preferencias_end_to_end(tmp_path, monkeypatch):
    import db
    import schema_v3
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v3.migrate()
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "A", "nombre": "Sala modular", "organismo": "Muni Fav",
                                 "region": "Maule"})
        db.upsert_licitacion(c, {"codigo": "B", "nombre": "Baños", "organismo": "Muni Otra",
                                 "region": "Ñuble"})
    plan.registrar_engagement("A")
    plan.registrar_engagement("A")   # dos veces sobre Muni Fav / Maule / modular
    plan.registrar_engagement("B")   # una sobre Muni Otra
    p = plan.preferencias()
    # el más atendido pesa MÁS (ya no "el máximo": la evidencia se gana, ver confianza ponderada)
    assert p["organismo"]["Muni Fav"] > p["organismo"]["Muni Otra"] > 0
    assert p["organismo"]["Muni Fav"] < plan.PESO_PREF          # 2 decisiones no llegan al tope
    assert p["tipo"].get("modular", 0) > 0 and "bano" in p["tipo"]


def test_pref_boost_no_aplasta_el_deadline():
    # aunque el usuario prefiera comprador+región+tipo a la vez, el boost total no supera PESO_PREF
    l = _lic("A", org="Muni Fav", reg="Maule", tipoProd="modular")
    prefs = {"organismo": {"Muni Fav": plan.PESO_PREF}, "region": {"Maule": plan.PESO_PREF},
             "tipo": {"modular": plan.PESO_PREF}}
    assert plan._pref_boost(l, prefs) == plan.PESO_PREF          # capeado, no 3×


def test_preferencias_ignora_comportamiento_viejo(tmp_path, monkeypatch):
    import datetime
    import db
    import schema_v3
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v3.migrate()
    viejo = (datetime.datetime.now() - datetime.timedelta(days=plan.DIAS_PREF + 5)).strftime("%Y-%m-%d %H:%M:%S")
    with db.conn() as c:
        c.execute("INSERT INTO plan_feedback (codigo, organismo, region, tipo_producto, ts) "
                  "VALUES (?,?,?,?,?)", ("Z", "Muni Vieja", "Maule", "modular", viejo))
    assert plan.preferencias() == {"organismo": {}, "region": {}, "tipo": {}}  # fuera de ventana


def test_preferencia_por_usuario(tmp_path, monkeypatch):
    # cada usuario aprende de SU comportamiento; el que no tiene historia cae al global (Fase 4)
    import db
    import schema_v3
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v3.migrate()
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "A", "nombre": "Sala modular", "organismo": "Muni Ana",
                                 "region": "Maule"})
        db.upsert_licitacion(c, {"codigo": "B", "nombre": "Baños", "organismo": "Muni Beto",
                                 "region": "Ñuble"})
    plan.registrar_engagement("A", usuario="ana")
    plan.registrar_engagement("B", usuario="beto")
    assert list(plan.preferencias("ana")["organismo"]) == ["Muni Ana"]      # cada uno aprende el suyo
    assert list(plan.preferencias("beto")["organismo"]) == ["Muni Beto"]
    assert plan.preferencias("ana")["organismo"]["Muni Ana"] > 0
    glob = plan.preferencias("carla")["organismo"]       # sin historia → comportamiento global
    assert set(glob) == {"Muni Ana", "Muni Beto"}


def test_usuario_dict_de_sesion_no_rompe(tmp_path, monkeypatch):
    """Regresión del crash en producción: la UI guarda el usuario como dict {username, nombre, rol}
    y se pasaba crudo a la query → sqlite3.ProgrammingError "type 'dict' is not supported" y el
    tablero ENTERO no cargaba. preferencias/registrar_engagement deben aceptar dict o str."""
    import db
    import schema_v3
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v3.migrate()
    sesion = {"username": "martin", "nombre": "Martín Testa", "rol": "admin"}
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "A", "nombre": "Sala modular", "organismo": "Muni X",
                                 "region": "Maule"})
    plan.registrar_engagement("A", usuario=sesion)          # antes: ProgrammingError
    assert plan.preferencias(sesion)["organismo"]["Muni X"] > 0
    assert plan.preferencias("martin")["organismo"]["Muni X"] > 0        # str sigue funcionando
    assert plan._usuario_id(None) is None and plan._usuario_id({}) is None


def _db(tmp_path, monkeypatch, lics=(("A", "Sala modular", "Muni A", "Maule"),)):
    import db
    import schema_v3
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v3.migrate()
    with db.conn() as c:
        for cod, nom, org, reg in lics:
            db.upsert_licitacion(c, {"codigo": cod, "nombre": nom, "organismo": org, "region": reg})
    return db


# ---------------------------------------------------- Fase 1 motor adaptativo: la evidencia se gana
def test_una_sola_decision_no_se_lleva_el_tope(tmp_path, monkeypatch):
    """Bug de diseño: se normalizaba dividiendo por el MÁXIMO, así que la única clave con feedback
    era su propio máximo y se llevaba PESO_PREF completo. Un click valía tanto como cincuenta."""
    _db(tmp_path, monkeypatch)
    plan.registrar_engagement("A", usuario="u")
    p = plan.preferencias("u")
    boost = p["organismo"]["Muni A"]
    assert 0 < boost < plan.PESO_PREF * 0.2, f"1 decisión no debe acercarse al tope (dio {boost})"


def test_la_confianza_crece_con_la_evidencia(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    vistos = []
    for i in range(36):
        plan.registrar_engagement("A", usuario="u")
        if i + 1 in (3, 12, 36):
            vistos.append(plan.preferencias("u")["organismo"]["Muni A"])
    assert vistos[0] < vistos[1] < vistos[2], "más evidencia debe pesar más"
    assert vistos[2] < plan.PESO_PREF          # nunca supera el tope
    assert vistos[2] > plan.PESO_PREF * 0.6    # con 36 decisiones ya pesa de verdad


def test_el_rechazo_es_evidencia_negativa(tmp_path, monkeypatch):
    """Un rechazo con motivo debe BAJAR al comprador, no solo dejar de subirlo."""
    _db(tmp_path, monkeypatch)
    for _ in range(5):
        plan.registrar_rechazo("A", usuario="u", motivo="muy lejos")
    p = plan.preferencias("u")
    assert p["organismo"]["Muni A"] < 0, "el rechazo debe dar peso negativo"
    l = _lic("A", org="Muni A", reg="Maule")
    assert plan._pref_boost(l, p) < 0                      # hunde
    assert plan._pref_boost(l, p) >= -plan.PESO_PREF       # pero acotado


def test_el_aprendizaje_nunca_entierra_un_deadline():
    """INVARIANTE: por mucho que el usuario rechace un comprador/región/tipo, algo que cierra
    MAÑANA tiene que seguir arriba de algo sin apuro. El aprendizaje inclina, no manda."""
    odiada = _lic("ODIADA", org="X", reg="R", tipoProd="t", dias=1, score=70)
    amada = _lic("AMADA", org="Y", reg="S", tipoProd="u", dias=None, score=70)
    prefs = {"organismo": {"X": -plan.PESO_PREF, "Y": plan.PESO_PREF},
             "region": {"R": -plan.PESO_PREF, "S": plan.PESO_PREF},
             "tipo": {"t": -plan.PESO_PREF, "u": plan.PESO_PREF}}
    res = plan.construir({"ODIADA": odiada, "AMADA": amada}, prefs=prefs)
    assert res[0]["codigo"] == "ODIADA"                        # el deadline manda igual
    assert plan._pref_boost(odiada, prefs) == -plan.PESO_PREF  # acotado aunque sean 3 ejes


def test_correccion_pesa_mas_que_un_click(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch, lics=(("A", "Sala modular", "Muni A", "Maule"),
                                     ("B", "Sala modular", "Muni B", "Maule")))
    plan.registrar_engagement("A", usuario="u")           # click
    plan.registrar_correccion("B", usuario="u", motivo="ajustó cantidades")
    p = plan.preferencias("u")
    assert p["organismo"]["Muni B"] > p["organismo"]["Muni A"]


def test_preferencias_explica_su_evidencia(tmp_path, monkeypatch):
    """Explicabilidad: el motor debe poder decir POR QUÉ subió algo."""
    _db(tmp_path, monkeypatch)
    for _ in range(4):
        plan.registrar_engagement("A", usuario="u")
    ev = plan.preferencias("u", detalle=True)["evidencia"]["organismo"]["Muni A"]
    assert ev["n"] == 4 and 0 < ev["confianza"] < 1


def test_backfill_reconstruye_historia_desde_eventos(tmp_path, monkeypatch):
    """El motor no debe arrancar en cero teniendo decisiones humanas ya registradas en `eventos`."""
    db = _db(tmp_path, monkeypatch, lics=(("A", "Sala modular", "Muni A", "Maule"),
                                          ("B", "Container", "Muni B", "Ñuble")))
    with db.conn() as c:
        db.log_evento(c, "A", "agregada_manual", "alta manual por código")
        db.log_evento(c, "B", "cambio_estado", "revision -> descartada. es mobiliario, no construcción")
    r = plan.backfill_desde_eventos(usuario="u")
    assert r["alta_manual"] == 1 and r["rechazo"] == 1
    p = plan.preferencias("u")
    assert p["organismo"]["Muni A"] > 0        # el alta manual suma
    assert p["organismo"]["Muni B"] < 0        # el descarte resta
    assert plan.backfill_desde_eventos(usuario="u") == {"alta_manual": 0, "engagement": 0,
                                                        "rechazo": 0, "omitidos": 0}   # idempotente


def test_registrar_engagement_codigo_inexistente_no_rompe(tmp_path, monkeypatch):
    import db
    import schema_v3
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v3.migrate()
    plan.registrar_engagement("NO-EXISTE")            # no lanza
    assert plan.preferencias() == {"organismo": {}, "region": {}, "tipo": {}}
