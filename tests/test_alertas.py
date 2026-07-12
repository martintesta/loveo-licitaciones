"""Tests de M-2: alertas de deadline (cierre)."""
from datetime import datetime, timedelta

import alertas
from alertas import evaluar_alertas, alertas_pendientes

HOY = datetime(2026, 6, 8, 12, 0, 0)


def _detalle_cierre_en(dias):
    """Detalle mínimo con FechaCierre a `dias` de HOY (en el bloque Fechas)."""
    fecha = (HOY + timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%S")
    return {"Fechas": {"FechaCierre": fecha}}


def test_cierra_en_2_dias_alerta_true():
    a = evaluar_alertas(_detalle_cierre_en(2), hoy=HOY, umbral=5)
    assert a["dias_al_cierre"] == 2
    assert a["alerta_cierre"] is True


def test_cierra_en_20_dias_alerta_false():
    a = evaluar_alertas(_detalle_cierre_en(20), hoy=HOY, umbral=5)
    assert a["dias_al_cierre"] == 20
    assert a["alerta_cierre"] is False


def test_cierre_pasado_no_alerta():
    a = evaluar_alertas(_detalle_cierre_en(-3), hoy=HOY, umbral=5)
    assert a["dias_al_cierre"] == -3
    assert a["alerta_cierre"] is False


def test_alertas_pendientes_ordena_por_cierre():
    resultados = [
        {"codigo": "B", "dias_al_cierre": 4, "alerta_cierre": True, "alerta_visita": False},
        {"codigo": "A", "dias_al_cierre": 1, "alerta_cierre": True, "alerta_visita": False},
        {"codigo": "C", "dias_al_cierre": 30, "alerta_cierre": False, "alerta_visita": False},
    ]
    pend = alertas_pendientes(resultados)
    assert [r["codigo"] for r in pend] == ["A", "B"]


# ------------------------------------------------------------- cobertura adicional (bordes y fallbacks)
def _en(dias):
    return (HOY + timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%S")


def test_parse_fecha_iso_fracciones_y_basura():
    assert alertas._parse_fecha("2026-06-22T16:00:00") == datetime(2026, 6, 22, 16, 0, 0)
    assert alertas._parse_fecha("2026-06-22T16:00:00.500-04:00") == datetime(2026, 6, 22, 16, 0, 0)
    assert alertas._parse_fecha(None) is None
    assert alertas._parse_fecha("no es fecha") is None


def test_fecha_cierre_fallback_al_top_level():
    # Fechas.FechaCierre en None → usa el FechaCierre de primer nivel (visto en vivo)
    d = {"Fechas": {"FechaCierre": None}, "FechaCierre": "2026-07-20T16:00:00"}
    assert alertas.fecha_cierre(d) == "2026-07-20T16:00:00"
    assert alertas.fecha_cierre({}) is None


def test_dias_hasta_signo_y_none():
    assert alertas.dias_hasta(_en(5), hoy=HOY) == 5
    assert alertas.dias_hasta(_en(0), hoy=HOY) == 0
    assert alertas.dias_hasta(_en(-5), hoy=HOY) == -5
    assert alertas.dias_hasta(None, hoy=HOY) is None


def test_alerta_justo_en_el_umbral_prende():
    a = evaluar_alertas({"Fechas": {"FechaCierre": _en(5)}}, hoy=HOY, umbral=5)
    assert a["dias_al_cierre"] == 5 and a["alerta_cierre"] is True   # 0 <= 5 <= 5


def test_alerta_visita_independiente_del_cierre():
    det = {"Fechas": {"FechaCierre": _en(40), "FechaVisitaTerreno": _en(1)}}
    a = evaluar_alertas(det, hoy=HOY, umbral=5)
    assert a["alerta_cierre"] is False                     # cierre lejos
    assert a["alerta_visita"] is True and a["dias_a_visita"] == 1


def test_sin_fechas_no_rompe_ni_alerta():
    a = evaluar_alertas({}, hoy=HOY, umbral=5)
    assert a["dias_al_cierre"] is None and a["alerta_cierre"] is False
    assert a["dias_a_visita"] is None and a["alerta_visita"] is False
    assert a["fecha_cierre"] == "" and a["fecha_visita"] == ""


def test_pendientes_incluye_solo_visita_y_pone_none_al_final():
    res = [
        {"codigo": "cierre1", "dias_al_cierre": 1, "alerta_cierre": True, "alerta_visita": False},
        {"codigo": "solo_visita", "dias_al_cierre": None, "alerta_cierre": False, "alerta_visita": True},
        {"codigo": "fuera", "dias_al_cierre": 30, "alerta_cierre": False, "alerta_visita": False},
    ]
    pend = alertas_pendientes(res)
    # 'fuera' excluida (sin alerta); solo_visita (dias_al_cierre None) ordena DESPUÉS de cierre1
    assert [r["codigo"] for r in pend] == ["cierre1", "solo_visita"]
