"""Tests de prescore: etiqueta de triage.

OJO: `prescore.py` NO lo llama nadie — el camino vivo es scoring.score_provisional y, desde
ago-2026, triage.evaluar. Quedó de cuando la base era Puerto Montt y su geografía está invertida
respecto de la operación actual: trata la Región Metropolitana como FUERA-DE-ZONA cuando ahora
es la más cercana a Pirque. Los tests se dejan describiendo lo que el módulo hace hoy, no lo que
debería hacer, para que la suite no mienta mientras se decide si se actualiza o se borra.
"""
from prescore import prescore


def test_fuera_de_zona():
    det = {
        "Nombre": "Suministro de container modular",
        "Modalidad": "1",
        "Comprador": {"RegionUnidad": "Región Metropolitana de Santiago"},
    }
    ps = prescore(det)
    assert ps["etiqueta"] == "FUERA-DE-ZONA"
    assert ps["suma_tiers"] is None


def test_los_lagos_desde_pirque_ya_no_es_prioritaria():
    """Con la base en Pirque, Los Lagos pasa de tier 1 a tier 3: 1.000 km en vez de 30.
    Es el mismo cambio que movió tres veredictos financieros."""
    det = {
        "Nombre": "Suministro de container modular para posta rural",
        "Modalidad": "1",
        "Comprador": {"RegionUnidad": "Región de Los Lagos"},
    }
    ps = prescore(det)
    assert ps["region_sur"] == "los lagos"
    assert ps["tier_logistica"] == 3        # era 1 cuando la base era Puerto Montt
    assert ps["tier_cashflow"] == 1
    assert ps["tier_alineacion"] == 1
    assert ps["suma_tiers"] == 5
    assert ps["etiqueta"] == "REVISAR"
