"""Tests de prescore: etiqueta de triage."""
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


def test_los_lagos_pago_al_dia_dos_keywords_prioritaria():
    # Los Lagos (logística tier 1 desde puerto_montt) + pago tier 1 (Modalidad=1)
    # + 2 keywords ("container", "modular") => alineación tier 1 => suma 3 <= 4.
    det = {
        "Nombre": "Suministro de container modular para posta rural",
        "Modalidad": "1",
        "Comprador": {"RegionUnidad": "Región de Los Lagos"},
    }
    ps = prescore(det)
    assert ps["region_sur"] == "los lagos"
    assert ps["tier_logistica"] == 1
    assert ps["tier_cashflow"] == 1
    assert ps["tier_alineacion"] == 1
    assert ps["suma_tiers"] == 3
    assert ps["etiqueta"] == "PRIORITARIA"
