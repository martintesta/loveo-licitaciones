"""Tests de filters: keywords (límite de palabra) y admisibilidad.

Herméticos: las keywords se FIJAN en un fixture (no dependen de config_local.py, que es
privado y no existe en CI). Acá se prueba la LÓGICA de matching, no la calibración real.
"""
import pytest

import filters
from filters import pasa_keywords, admisibilidad


@pytest.fixture(autouse=True)
def _keywords_fijas(monkeypatch):
    monkeypatch.setattr(filters, "KEYWORDS_INCLUIR",
                        ["reas", "box dental", "prefabricad", "modulo", "container", "modular"])
    monkeypatch.setattr(filters, "KEYWORDS_EXCLUIR", ["capacitacion", "areas verdes"])
    monkeypatch.setattr(filters, "KEYWORDS_AMPLIO", [])


def test_areas_no_matchea_reas():
    # "reas" NO debe matchear dentro de "áreas" (límite de palabra a la izquierda).
    assert pasa_keywords("Servicio de aseo en áreas verdes") is False


def test_reas_como_palabra_si_matchea():
    assert pasa_keywords("Retiro de residuos REAS peligrosos") is True


def test_box_dentales_matchea_box_dental():
    # "box dental" (singular) debe matchear "box dentales" (plural) por prefijo.
    assert pasa_keywords("Arriendo de box dentales") is True


def test_prefabricad_matchea_prefabricado():
    # La raíz "prefabricad" debe matchear "prefabricado".
    assert pasa_keywords("Suministro de galpón prefabricado") is True


def test_modulo_de_capacitacion_excluido():
    assert pasa_keywords("Entrega de módulo de capacitación") is False


def test_admisibilidad_subcontratacion_cero_inadmisible():
    det = {"SubContratacion": "0"}
    es_admisible, motivos = admisibilidad(det)
    assert es_admisible is False
    assert any("subcontrat" in m.lower() for m in motivos)


def test_admisibilidad_prohibicion_es_bandera_no_rechazo():
    det = {
        "SubContratacion": "1",
        "ProhibicionContratacion": (
            "El proveedor no podrá ceder ni transferir el contrato sin "
            "autorización previa."
        ),
    }
    es_admisible, motivos = admisibilidad(det)
    assert es_admisible is True
    assert any("bandera" in m.lower() for m in motivos)
