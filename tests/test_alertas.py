"""Tests de M-2: alertas de deadline (cierre)."""
from datetime import datetime, timedelta

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
