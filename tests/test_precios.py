"""
test_precios.py — Sensor del catálogo de precios (precios.py).

Las tres reglas del catálogo, cada una con su test:
  1. NUNCA se pisa un precio: cada cotización es un punto nuevo con fecha (día y HORA), y conviven.
  2. Todo precio guarda de dónde salió: `fuente` + `source_url` con el link.
  3. La corrección manual manda y el refresco mensual no la atropella.

Ningún test toca la red: `buscar` es inyectable.

  python -m pytest tests/test_precios.py -q
"""
import datetime

import db
import precios
import schema_v3

DESC = "Container oficina modular nuevo con baño simple completo"


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v3.migrate()


def _viejo(desc, precio, dias, fuente="web", url=None):
    """Un punto con fecha hacia atrás, para poder probar el vencimiento."""
    ts = (datetime.datetime.now() - datetime.timedelta(days=dias)).isoformat(sep=" ", timespec="seconds")
    import cubicacion
    with db.conn() as c:
        c.execute("INSERT INTO precios_referencia (descripcion, descripcion_norm, unidad, "
                  "precio_unitario, fuente, fecha, source_url) VALUES (?,?,?,?,?,?,?)",
                  (desc, cubicacion._na(desc), "un", precio, fuente, ts, url))


# ------------------------------------------------------------------ 1. append-only con hora
def test_cada_cotizacion_es_un_punto_nuevo_no_un_update(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    precios.registrar(DESC, 3_051_000, fuente="valentina")
    precios.registrar(DESC, 3_200_000, fuente="web", url="https://x.cl/p")
    h = precios.historial(DESC)
    assert len(h) == 2, "el precio viejo tiene que seguir existiendo"
    assert h[0]["precio_unitario"] == 3_200_000       # el más nuevo primero
    assert h[1]["precio_unitario"] == 3_051_000


def test_la_fecha_guarda_dia_y_hora(tmp_path, monkeypatch):
    """Sin hora, dos cotizaciones del mismo día no se pueden ordenar y la tendencia miente."""
    _setup(tmp_path, monkeypatch)
    r = precios.registrar(DESC, 100, fuente="manual")
    assert len(r["fecha"]) == 19 and ":" in r["fecha"]      # 'YYYY-MM-DD HH:MM:SS'
    datetime.datetime.fromisoformat(r["fecha"])            # parsea o revienta


def test_dos_precios_del_mismo_dia_conviven_y_se_ordenan(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    precios.registrar(DESC, 1_000, fuente="web")
    precios.registrar(DESC, 2_000, fuente="web")
    h = precios.historial(DESC)
    assert [x["precio_unitario"] for x in h] == [2_000, 1_000]


def test_el_catalogo_toma_el_ultimo_punto(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    precios.registrar(DESC, 3_051_000, fuente="valentina")
    precios.registrar(DESC, 3_400_000, fuente="web", url="https://x.cl/p")
    import cubicacion
    cat = precios.catalogo()
    assert cat[cubicacion._na(DESC)]["precio_unitario"] == 3_400_000


# ------------------------------------------------------------------ 2. trazabilidad
def test_el_precio_web_guarda_el_link(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _viejo(DESC, 3_000_000, dias=100)

    def buscar(desc, unidad=None):
        return {"precio": 3_300_000, "url": "https://espaciomodular.cl/oficina-container"}

    r = precios.refrescar(buscar=buscar)
    assert r["actualizados"] == 1
    ultimo = precios.historial(DESC)[0]
    assert ultimo["source_url"] == "https://espaciomodular.cl/oficina-container"
    assert ultimo["fuente"] == "web"


def test_la_correccion_manual_puede_llevar_link_y_nota(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = precios.corregir(DESC, "3.250.000", url="https://prov.cl/cotiz", nota="cotización Prov X")
    assert r["ok"] and r["precio"] == 3_250_000      # entiende el formato CLP que uno tipea
    ultimo = precios.historial(DESC)[0]
    assert ultimo["fuente"] == "manual"
    assert ultimo["source_url"] == "https://prov.cl/cotiz"
    assert "cotización Prov X" in ultimo["descripcion"]


def test_un_precio_invalido_se_rechaza(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert not precios.corregir(DESC, "no es un precio")["ok"]
    assert not precios.corregir(DESC, -5)["ok"]
    assert not precios.corregir("", 1000)["ok"]


# ------------------------------------------------------------------ 3. vencimiento y precedencia
def test_solo_se_re_cotiza_lo_vencido(tmp_path, monkeypatch):
    """El job mensual no re-cotiza todo el catálogo: solo lo que se puso viejo. Si no, cada corrida
    gasta 90 búsquedas web para reconfirmar lo que ya sabíamos."""
    _setup(tmp_path, monkeypatch)
    _viejo("Material fresco", 1_000, dias=5, fuente="web")
    _viejo("Material vencido", 2_000, dias=90, fuente="web")
    pendientes = [x["descripcion"] for x in precios.vencidos()]
    assert pendientes == ["Material vencido"]


def test_un_precio_pagado_de_verdad_aguanta_mas_que_una_estimacion(tmp_path, monkeypatch):
    """Lo que Loveo pagó ('valentina') o corrigió a mano no es una estimación de mercado: no lo
    vence el mismo reloj que a una cotización web."""
    _setup(tmp_path, monkeypatch)
    _viejo("Estimación web", 1_000, dias=60, fuente="web")
    _viejo("Precio pagado", 2_000, dias=60, fuente="valentina")
    _viejo("Corregido a mano", 3_000, dias=60, fuente="manual")
    pendientes = [x["descripcion"] for x in precios.vencidos()]
    assert pendientes == ["Estimación web"]


def test_una_correccion_manual_reciente_sobrevive_al_refresco(tmp_path, monkeypatch):
    """Si Martín corrige un precio, el job mensual no se lo pisa a la semana siguiente."""
    _setup(tmp_path, monkeypatch)
    _viejo(DESC, 3_000_000, dias=200, fuente="web")
    precios.corregir(DESC, 3_500_000, nota="cotización firme")

    def buscar(desc, unidad=None):
        raise AssertionError("no debería re-cotizar un precio corregido a mano hace un rato")

    r = precios.refrescar(buscar=buscar)
    assert r["revisados"] == 0
    import cubicacion
    assert precios.catalogo()[cubicacion._na(DESC)]["precio_unitario"] == 3_500_000


def test_todos_ignora_el_vencimiento(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _viejo("Fresco", 1_000, dias=1, fuente="web")
    assert precios.vencidos() == []
    assert len(precios.vencidos(todos=True)) == 1


# ------------------------------------------------------------------ el job
def test_el_refresco_reporta_la_variacion_de_cada_precio(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _viejo("Sube", 1_000, dias=90, fuente="web")
    _viejo("Baja", 1_000, dias=90, fuente="web")

    def buscar(desc, unidad=None):
        return {"precio": 1_500 if desc == "Sube" else 500, "url": f"https://x.cl/{desc}"}

    r = precios.refrescar(buscar=buscar)
    cambios = {c["descripcion"]: c for c in r["cambios"]}
    assert cambios["Sube"]["variacion_pct"] == 50.0 and cambios["Sube"]["direccion"] == "sube"
    assert cambios["Baja"]["variacion_pct"] == -50.0 and cambios["Baja"]["direccion"] == "baja"


def test_si_la_web_no_encuentra_nada_el_precio_viejo_sigue_valiendo(tmp_path, monkeypatch):
    """Nunca dejar un material SIN precio por una búsqueda fallida: un costo faltante rompe el margen."""
    _setup(tmp_path, monkeypatch)
    _viejo(DESC, 3_000_000, dias=90, fuente="web", url="https://viejo.cl")

    r = precios.refrescar(buscar=lambda d, u=None: None)
    assert r["actualizados"] == 0 and DESC in r["sin_precio"]
    import cubicacion
    assert precios.catalogo()[cubicacion._na(DESC)]["precio_unitario"] == 3_000_000


def test_una_busqueda_que_revienta_no_frena_al_resto(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _viejo("Rompe", 1_000, dias=90, fuente="web")
    _viejo("Anda", 1_000, dias=90, fuente="web")

    def buscar(desc, unidad=None):
        if desc == "Rompe":
            raise RuntimeError("timeout")
        return {"precio": 1_200, "url": "https://x.cl"}

    r = precios.refrescar(buscar=buscar)
    assert r["actualizados"] == 1 and "Rompe" in r["sin_precio"]


def test_el_limite_acota_el_gasto(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    for i in range(5):
        _viejo(f"Material {i}", 1_000, dias=90, fuente="web")
    llamadas = []

    def buscar(desc, unidad=None):
        llamadas.append(desc)
        return {"precio": 1_100, "url": "https://x.cl"}

    precios.refrescar(limite=2, buscar=buscar)
    assert len(llamadas) == 2


def test_la_busqueda_web_se_puede_apagar(monkeypatch):
    monkeypatch.setenv("LOVEO_PRECIOS_WEB", "0")
    assert precios.buscar_precio_web("lo que sea") is None


def test_cubicacion_ia_y_el_job_mensual_cotizan_por_el_mismo_lugar(monkeypatch):
    """Una sola fuente de búsqueda: si divergieran, el precio guardado al preciar un BOM y el del
    refresco mensual saldrían de prompts distintos y el catálogo quedaría inconsistente."""
    import cubicacion_ia
    llamado = {}
    monkeypatch.setattr(precios, "buscar_precio_web",
                        lambda d, u=None: llamado.setdefault("desc", d) or {"precio": 1, "url": "u"})
    cubicacion_ia._buscar_web_real("Panel SIP", "m2")
    assert llamado["desc"] == "Panel SIP"
