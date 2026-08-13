"""
test_visitas.py — Sensor de la detección de visita a terreno EN LA INGESTA (no en la Capa C).

El agujero que cubren estos tests costó cinco licitaciones en un solo lote de agosto de 2026:
`Fechas.FechaVisitaTerreno` del API viene null siempre, la visita está escrita en el pliego, y
la detección corría tan tarde (al analizar) que la visita ya había pasado.

SQLite temporal, sin red y sin OCR: los "documentos" son .txt, que `bases.documento_a_texto`
lee directo.

  python -m pytest tests/test_visitas.py -q
"""
import json
from datetime import datetime, timedelta

import db
import ingest_bases
import schema_v3
import visitas


PLIEGO_OBLIGATORIA = """
BASES ADMINISTRATIVAS
Artículo 9. VISITA A TERRENO. Se realizará una visita a terreno de carácter OBLIGATORIA
el día 12 de agosto de 2026 a las 10:00 horas en dependencias del establecimiento.
La inasistencia dejará la oferta inadmisible y no será evaluada.
"""

PLIEGO_SIN_VISITA = """
BASES ADMINISTRATIVAS
Artículo 9. De la presentación de las ofertas. Las ofertas se presentarán únicamente
a través del portal, en formato PDF, dentro del plazo señalado en el cronograma.
"""

PLIEGO_PROHIBIDA = """
BASES ADMINISTRATIVAS
VISITA DE TERRENO: No se contempla, se adjunta video explicativo del recinto.
"""


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "STORAGE_DIR", tmp_path / "storage")
    db.init_db()
    schema_v3.migrate()


def _lic(codigo, **campos):
    """Alta mínima de una licitación vigente y admisible."""
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": codigo, "nombre": campos.pop("nombre", "Módulos")})
        sets = ", ".join(f"{k}=?" for k in campos)
        if sets:
            c.execute(f"UPDATE licitaciones SET {sets} WHERE codigo=?",
                      (*campos.values(), codigo))


def _carpeta(raiz, codigo, archivos):
    sub = raiz / codigo
    sub.mkdir(parents=True, exist_ok=True)
    for nombre, texto in archivos.items():
        (sub / nombre).write_text(texto, encoding="utf-8")
    return sub


# --------------------------- caracter() ------------------------------------

def test_caracter_colapsa_el_dict_a_un_valor():
    assert visitas.caracter({"menciona": False}) == "sin_visita"
    assert visitas.caracter(None) == "sin_visita"
    assert visitas.caracter({"menciona": True}) == "voluntaria"
    assert visitas.caracter({"menciona": True, "puntuada": True}) == "puntuada"
    assert visitas.caracter({"menciona": True, "obligatoria": True}) == "obligatoria"


def test_prohibida_gana_sobre_obligatoria():
    """Si el pliego dice expresamente que no se contempla, eso manda sobre el boilerplate.
    Es el caso real de Cabildo, que daba EXCLUYENTE por una cláusula condicional."""
    vis = {"menciona": True, "obligatoria": True, "puntuada": True, "prohibida": True}
    assert visitas.caracter(vis) == "prohibida"


def test_obligatoria_gana_sobre_puntuada():
    """Obligatoria decide admisibilidad; puntuada sólo cuesta puntaje. La peor manda."""
    assert visitas.caracter({"menciona": True, "obligatoria": True, "puntuada": True}) == "obligatoria"


def test_urgencia_solo_para_lo_accionable():
    assert "inadmisible" in visitas.urgencia("obligatoria")
    assert visitas.urgencia("sin_visita") is None
    assert visitas.urgencia("prohibida") is None


# --------------------------- detección -------------------------------------

def test_detecta_y_persiste_al_ingestar(tmp_path, monkeypatch):
    """El corazón del fix: al registrar las bases queda escrito el carácter de la visita."""
    _setup(tmp_path, monkeypatch)
    _lic("1234-5-LE26")
    raiz = tmp_path / "bases"
    _carpeta(raiz, "1234-5-LE26", {"bases_administrativas.txt": PLIEGO_OBLIGATORIA})

    r = ingest_bases.desde_local(str(raiz))
    assert r["ok"] and r["registrados"] == 1
    assert r["visitas"]["detectadas"] == 1
    assert r["visitas"]["con_visita"][0]["codigo"] == "1234-5-LE26"
    assert r["visitas"]["con_visita"][0]["caracter"] == "obligatoria"

    with db.conn() as c:
        f = c.execute("SELECT visita_caracter, visita_fecha_txt, visita_fragmento, "
                      "visita_detectada_at FROM licitaciones WHERE codigo='1234-5-LE26'").fetchone()
    assert f["visita_caracter"] == "obligatoria"
    assert f["visita_detectada_at"]
    assert "12 de agosto de 2026" in (f["visita_fecha_txt"] or "")
    assert "OBLIGATORIA" in f["visita_fragmento"]


def test_sin_visita_tambien_se_persiste(tmp_path, monkeypatch):
    """'sin_visita' no es lo mismo que NULL: significa que SÍ se leyó el pliego y no la menciona.
    Sin esta distinción no se puede saber si falta leer o si ya se leyó."""
    _setup(tmp_path, monkeypatch)
    _lic("1234-6-LE26")
    raiz = tmp_path / "bases"
    _carpeta(raiz, "1234-6-LE26", {"bases.txt": PLIEGO_SIN_VISITA})
    ingest_bases.desde_local(str(raiz))
    with db.conn() as c:
        f = c.execute("SELECT visita_caracter FROM licitaciones WHERE codigo='1234-6-LE26'").fetchone()
    assert f["visita_caracter"] == "sin_visita"


def test_pliego_que_niega_la_visita_no_alarma(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _lic("1234-7-LE26")
    raiz = tmp_path / "bases"
    _carpeta(raiz, "1234-7-LE26", {"bases.txt": PLIEGO_PROHIBIDA})
    r = ingest_bases.desde_local(str(raiz))
    assert r["visitas"]["con_visita"] == []
    with db.conn() as c:
        f = c.execute("SELECT visita_caracter FROM licitaciones WHERE codigo='1234-7-LE26'").fetchone()
    assert f["visita_caracter"] == "prohibida"


def test_ignora_nuestro_propio_excel_de_analisis(tmp_path, monkeypatch):
    """REGRESIÓN: el Excel de análisis que genera la skill cita el pliego entero, cláusula de
    visita incluida. Si el detector lo leyera, se estaría confirmando con su propia salida."""
    _setup(tmp_path, monkeypatch)
    _lic("1234-8-LE26")
    raiz = tmp_path / "bases"
    _carpeta(raiz, "1234-8-LE26", {
        "bases.txt": PLIEGO_SIN_VISITA,
        "Analisis_1234-8-LE26_2026-08-08.txt": PLIEGO_OBLIGATORIA,   # nuestra propia salida
    })
    ingest_bases.desde_local(str(raiz))
    with db.conn() as c:
        f = c.execute("SELECT visita_caracter FROM licitaciones WHERE codigo='1234-8-LE26'").fetchone()
    assert f["visita_caracter"] == "sin_visita"


def test_licitacion_sin_documentos_queda_en_null(tmp_path, monkeypatch):
    """Sin bases no hay veredicto: NULL, no 'sin_visita'. Esas son las que alerta en_riesgo()."""
    _setup(tmp_path, monkeypatch)
    _lic("1234-9-LE26")
    assert visitas.detectar_y_guardar("1234-9-LE26") is None
    with db.conn() as c:
        f = c.execute("SELECT visita_caracter FROM licitaciones WHERE codigo='1234-9-LE26'").fetchone()
    assert f["visita_caracter"] is None


def test_un_documento_ilegible_no_frena_al_resto(tmp_path, monkeypatch):
    """Un anexo roto no puede hacer perder la cláusula que sí está en las bases."""
    _setup(tmp_path, monkeypatch)
    _lic("1234-10-LE26")
    raiz = tmp_path / "bases"
    sub = _carpeta(raiz, "1234-10-LE26", {"bases.txt": PLIEGO_OBLIGATORIA})
    (sub / "anexo_roto.pdf").write_bytes(b"esto no es un PDF")
    ingest_bases.desde_local(str(raiz))
    with db.conn() as c:
        f = c.execute("SELECT visita_caracter FROM licitaciones WHERE codigo='1234-10-LE26'").fetchone()
    assert f["visita_caracter"] == "obligatoria"


def test_backfill_respeta_el_presupuesto(tmp_path, monkeypatch):
    """La ingesta diaria no puede convertirse en una corrida de OCR de horas: las que ya estaban
    registradas se rellenan de a poco, las que traen documentos nuevos van siempre."""
    _setup(tmp_path, monkeypatch)
    raiz = tmp_path / "bases"
    for i in range(4):
        cod = f"20{i}-1-LE26"
        _lic(cod)
        _carpeta(raiz, cod, {"bases.txt": PLIEGO_OBLIGATORIA})
    ingest_bases.desde_local(str(raiz))          # primera pasada: todas traen documentos nuevos
    with db.conn() as c:                          # las vuelvo a dejar sin veredicto
        c.execute("UPDATE licitaciones SET visita_caracter=NULL")

    r = visitas.al_ingestar([], [f"20{i}-1-LE26" for i in range(4)], max_backfill=2)
    assert r["detectadas"] == 2 and r["backfill_pendiente"] == 2


def test_backfill_corta_por_reloj(tmp_path, monkeypatch):
    """El costo real no lo manda la cantidad de licitaciones sino cuántas traen pliego escaneado:
    una con OCR puede tardar más que veinte con capa de texto. Por eso el tope es también de reloj."""
    _setup(tmp_path, monkeypatch)
    raiz = tmp_path / "bases"
    for i in range(5):
        cod = f"21{i}-1-LE26"
        _lic(cod)
        _carpeta(raiz, cod, {"bases.txt": PLIEGO_OBLIGATORIA})
    ingest_bases.desde_local(str(raiz))
    with db.conn() as c:
        c.execute("UPDATE licitaciones SET visita_caracter=NULL")

    # arranque=0 · chequeo de la 1ª=0 (pasa) · chequeo de la 2ª=99 (corta) · lectura final
    reloj = iter([0, 0, 99, 99])
    monkeypatch.setattr(visitas.time, "monotonic", lambda: next(reloj))
    r = visitas.al_ingestar([], [f"21{i}-1-LE26" for i in range(5)], max_segundos=10)
    assert r["detectadas"] == 1                       # cortó al agotarse el reloj
    assert r["backfill_pendiente"] == 4                # el resto queda para la corrida siguiente


def test_documentos_nuevos_no_los_frena_el_reloj(tmp_path, monkeypatch):
    """Lo recién ingestado se detecta SIEMPRE: es exactamente lo que acaba de cambiar, y es la
    única vía por la que una visita nueva puede aparecer hoy."""
    _setup(tmp_path, monkeypatch)
    raiz = tmp_path / "bases"
    for i in range(3):
        cod = f"22{i}-1-LE26"
        _lic(cod)
        _carpeta(raiz, cod, {"bases.txt": PLIEGO_OBLIGATORIA})
    ingest_bases.desde_local(str(raiz))
    with db.conn() as c:
        c.execute("UPDATE licitaciones SET visita_caracter=NULL")

    monkeypatch.setattr(visitas.time, "monotonic", lambda: 9999)   # reloj agotado desde el arranque
    r = visitas.al_ingestar([f"22{i}-1-LE26" for i in range(3)], [], max_segundos=0)
    assert r["detectadas"] == 3 and len(r["con_visita"]) == 3


# --------------------------- alertas ---------------------------------------

def _publicada_hace(dias):
    f = (datetime.now() - timedelta(days=dias)).isoformat(timespec="seconds")
    return json.dumps({"Fechas": {"FechaPublicacion": f, "FechaVisitaTerreno": None}})


def _cierra_en(dias):
    return (datetime.now() + timedelta(days=dias)).isoformat(timespec="seconds")


def test_en_riesgo_pesca_la_publicada_sin_bases(tmp_path, monkeypatch):
    """La alerta que faltaba: sin bases no se puede leer el pliego, y por eso mismo hay que avisar."""
    _setup(tmp_path, monkeypatch)
    _lic("3000-1-LE26", triage_senal="core", nombre="Módulos clínicos", admisible=1, vigente_oferta=1,
         estado_revision="nueva", score_provisional=80, docs_estado="pendiente",
         json_detalle=_publicada_hace(6), fecha_cierre=_cierra_en(5))
    r = visitas.en_riesgo()
    assert [x["codigo"] for x in r] == ["3000-1-LE26"]
    assert r[0]["dias_publicada"] == 6 and r[0]["dias_al_cierre"] == 5


def test_en_riesgo_ignora_las_que_ya_tienen_bases(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _lic("3000-2-LE26", triage_senal="core", admisible=1, vigente_oferta=1, estado_revision="nueva",
         score_provisional=80, docs_estado="descargado",
         json_detalle=_publicada_hace(6), fecha_cierre=_cierra_en(5))
    assert visitas.en_riesgo() == []


def test_en_riesgo_ignora_descartadas_y_recien_publicadas(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _lic("3000-3-LE26", triage_senal="core", admisible=1, vigente_oferta=1, estado_revision="descartada",
         score_provisional=90, docs_estado="pendiente",
         json_detalle=_publicada_hace(9), fecha_cierre=_cierra_en(5))
    _lic("3000-4-LE26", triage_senal="core", admisible=1, vigente_oferta=1, estado_revision="nueva",
         score_provisional=90, docs_estado="pendiente",
         json_detalle=_publicada_hace(0), fecha_cierre=_cierra_en(20))   # aún dentro de plazo
    assert visitas.en_riesgo() == []


def test_en_riesgo_ignora_lo_que_el_embudo_mato(tmp_path, monkeypatch):
    """No sirve alertar de lo que igual se va a descartar: la alerta se gasta y deja de leerse.

    ANTES esto lo decidía el score (<60 no alertaba). El score resultó ser mal juez: le daba
    60-84 a plazas, canchas y luminarias por su puntaje logístico, y la bandeja quedaba con 26
    avisos de los cuales ~22 eran ruido. Ahora decide el embudo, que descarta con un motivo."""
    _setup(tmp_path, monkeypatch)
    _lic("3000-5-LE26", admisible=1, vigente_oferta=1, estado_revision="nueva",
         score_provisional=84, docs_estado="pendiente",     # score ALTO y aun así no alerta
         triage_gate="producto", triage_senal="onu_fuera",
         json_detalle=_publicada_hace(9), fecha_cierre=_cierra_en(5))
    assert visitas.en_riesgo() == []


def test_en_riesgo_ordena_por_cierre_mas_proximo(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _lic("3000-6-LE26", triage_senal="core", admisible=1, vigente_oferta=1, estado_revision="nueva",
         score_provisional=70, docs_estado="pendiente",
         json_detalle=_publicada_hace(4), fecha_cierre=_cierra_en(9))
    _lic("3000-7-LE26", triage_senal="core", admisible=1, vigente_oferta=1, estado_revision="nueva",
         score_provisional=70, docs_estado="pendiente",
         json_detalle=_publicada_hace(4), fecha_cierre=_cierra_en(2))
    assert [x["codigo"] for x in visitas.en_riesgo()] == ["3000-7-LE26", "3000-6-LE26"]


def test_en_riesgo_usa_fecha_descubierta_si_falta_el_detalle(tmp_path, monkeypatch):
    """json_detalle puede faltar (alta manual, API caída). fecha_descubierta es buen proxy:
    run_daily corre a diario."""
    _setup(tmp_path, monkeypatch)
    vieja = (datetime.now() - timedelta(days=7)).isoformat(sep=" ", timespec="seconds")
    _lic("3000-8-LE26", triage_senal="core", admisible=1, vigente_oferta=1, estado_revision="nueva",
         score_provisional=70, docs_estado="pendiente", json_detalle=None,
         fecha_descubierta=vieja, fecha_cierre=_cierra_en(4))
    r = visitas.en_riesgo()
    assert len(r) == 1 and r[0]["dias_publicada"] == 7


def test_pendientes_de_visita_prioriza_la_excluyente(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _lic("4000-1-LE26", vigente_oferta=1, estado_revision="nueva", visita_caracter="puntuada",
         fecha_cierre=_cierra_en(2))
    _lic("4000-2-LE26", vigente_oferta=1, estado_revision="nueva", visita_caracter="obligatoria",
         fecha_cierre=_cierra_en(8))
    _lic("4000-3-LE26", vigente_oferta=1, estado_revision="nueva", visita_caracter="sin_visita",
         fecha_cierre=_cierra_en(1))
    r = visitas.pendientes_de_visita()
    assert [x["codigo"] for x in r] == ["4000-2-LE26", "4000-1-LE26"]   # excluyente primero
    assert "inadmisible" in r[0]["urgencia"]


def test_pendientes_de_visita_excluye_cerradas_y_descartadas(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _lic("4000-4-LE26", vigente_oferta=1, estado_revision="descartada",
         visita_caracter="obligatoria", fecha_cierre=_cierra_en(5))
    _lic("4000-5-LE26", vigente_oferta=1, estado_revision="nueva",
         visita_caracter="obligatoria", fecha_cierre=_cierra_en(-3))    # ya cerró
    assert visitas.pendientes_de_visita() == []


# --------------------------- cableado en run_daily -------------------------

def test_run_daily_expone_la_ventana_de_visita(tmp_path, monkeypatch):
    """La alerta tiene que salir del orquestador diario, no sólo existir como función suelta.
    Sin red: el listado va cacheado y sin detalles."""
    import run_daily
    _setup(tmp_path, monkeypatch)
    monkeypatch.delenv("LOVEO_BASES_LOCAL", raising=False)
    _lic("5000-1-LE26", triage_senal="core", admisible=1, vigente_oferta=1, estado_revision="nueva",
         score_provisional=90, docs_estado="pendiente",
         json_detalle=_publicada_hace(7), fecha_cierre=_cierra_en(3))

    r = run_daily.procesar_dia("08082026", listado=[], traer_detalles=False)
    riesgo = r["visita_terreno"]["sin_bases_en_riesgo"]
    assert [x["codigo"] for x in riesgo] == ["5000-1-LE26"]


def test_run_daily_no_se_cae_si_falla_la_deteccion(tmp_path, monkeypatch):
    """REGRESIÓN: el pipeline diario descubre y puntúa; una alerta rota no puede voltearlo."""
    import run_daily
    _setup(tmp_path, monkeypatch)
    monkeypatch.delenv("LOVEO_BASES_LOCAL", raising=False)
    monkeypatch.setattr(visitas, "en_riesgo", lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    r = run_daily.procesar_dia("08082026", listado=[], traer_detalles=False)
    assert "error" in r["visita_terreno"]          # se reporta, no se propaga
    assert r["candidatos"] == 0                    # el resto del pipeline corrió igual


# --------------------------- registros a medias ----------------------------

def test_cura_las_que_quedaron_sin_detalle(tmp_path, monkeypatch):
    """Sin fecha de cierre ningún filtro las saca: quedan 'vigentes' para siempre. Pasó con dos de
    junio de 2026, una de $160M con score 80 que nadie miró porque parecía ruido."""
    import run_daily
    _setup(tmp_path, monkeypatch)
    _lic("6000-1-LE26", vigente_oferta=1, json_detalle=None, fecha_cierre=None)
    _lic("6000-2-LE26", vigente_oferta=1, json_detalle=_publicada_hace(2),
         fecha_cierre=_cierra_en(5))                       # completa: no se toca

    vistos = []

    def _fake(codigo, manual=True):
        vistos.append(codigo)
        with db.conn() as c:
            c.execute("UPDATE licitaciones SET json_detalle='{}', fecha_cierre=?, vigente_oferta=0 "
                      "WHERE codigo=?", (_cierra_en(-30), codigo))
        return {"ok": True, "codigo": codigo, "score": 80}

    monkeypatch.setattr(run_daily, "procesar_codigo", _fake)
    monkeypatch.setattr(run_daily.time, "sleep", lambda s: None)
    r = run_daily._curar_sin_detalle()
    assert vistos == ["6000-1-LE26"]                       # sólo la incompleta
    assert r["completadas"] == [{"codigo": "6000-1-LE26", "score": 80}]
    assert r["pendientes"] == 0


def test_curar_sin_detalle_respeta_el_limite_y_aguanta_fallos(tmp_path, monkeypatch):
    import run_daily
    _setup(tmp_path, monkeypatch)
    for i in range(4):
        _lic(f"6100-{i}-LE26", vigente_oferta=1, json_detalle=None, fecha_cierre=None)

    def _fake(codigo, manual=True):
        raise RuntimeError("API caída")

    monkeypatch.setattr(run_daily, "procesar_codigo", _fake)
    monkeypatch.setattr(run_daily.time, "sleep", lambda s: None)
    r = run_daily._curar_sin_detalle(limite=2)
    assert len(r["fallidas"]) == 2 and r["completadas"] == []
    assert r["pendientes"] == 4                            # ninguna se pudo completar


# --------------------------------------------------------------------------------------------
# La alerta la gobierna el EMBUDO, no el score
# --------------------------------------------------------------------------------------------
# Con el score de 6 dimensiones la alerta tiraba 26 avisos, de los cuales ~22 eran plazas,
# canchas, luminarias y veredas: fuera de core, pero con score 60-84 porque la suma ponderada
# premia lo logístico. Una alerta que hay que filtrar a ojo deja de leerse — y ésta existe
# justamente porque perder una visita obligatoria descalifica. Pasó dos veces este mes.

def _sembrar(c, codigo, nombre, gate, senal, score, dias_pub=10):
    import datetime as _dt
    pub = (_dt.datetime.now() - _dt.timedelta(days=dias_pub)).strftime("%Y-%m-%d %H:%M:%S")
    cierre = (_dt.datetime.now() + _dt.timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO licitaciones(codigo, nombre, vigente_oferta, admisible, "
              "  estado_revision, docs_estado, score_provisional, triage_gate, triage_senal, "
              "  triage_motivo, fecha_cierre, fecha_descubierta, fecha_actualizada) "
              "VALUES (?,?,1,1,'nueva','pendiente',?,?,?,?,?,?,?)",
              (codigo, nombre, score, gate, senal, "motivo", cierre, pub, pub))


def test_la_alerta_ignora_lo_que_el_embudo_descarto(tmp_path, monkeypatch):
    """Una plaza con score 84 no puede seguir generando una alerta de visita."""
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "v.db")
    db.init_db()
    import schema_v3
    schema_v3.migrate()
    with db.conn() as c:
        _sembrar(c, "PLAZA-1", "MEJORAMIENTO PLAZA DE ARMAS", "producto", "onu_fuera", 84)
        _sembrar(c, "CONT-1", "ADQUISICION DE CONTAINERS", None, "core", 61)

    codigos = [x["codigo"] for x in visitas.en_riesgo()]
    assert "CONT-1" in codigos, "el producto core tiene que alertar"
    assert "PLAZA-1" not in codigos, "el embudo ya la descartó: no puede alertar"


def test_la_que_no_paso_por_el_embudo_no_alerta_a_ciegas(tmp_path, monkeypatch):
    """Sin veredicto del embudo no hay señal de que sea nuestro producto. Antes bastaba el score,
    que es exactamente lo que llenaba la bandeja de ruido."""
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "v2.db")
    db.init_db()
    import schema_v3
    schema_v3.migrate()
    with db.conn() as c:
        _sembrar(c, "SINEVAL-1", "ALGO CON SCORE ALTO", None, None, 90)

    assert [x["codigo"] for x in visitas.en_riesgo()] == []


def test_la_alerta_lleva_la_señal_del_embudo(tmp_path, monkeypatch):
    """Para poder decidir sin abrir la ficha hay que saber POR QUÉ entró."""
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "v3.db")
    db.init_db()
    import schema_v3
    schema_v3.migrate()
    with db.conn() as c:
        _sembrar(c, "CONT-2", "CONTAINERS OFICINA", None, "core", 61)

    a = visitas.en_riesgo()[0]
    assert a["senal"] == "motivo"
