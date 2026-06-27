"""Tests de M-1: clasificación de keywords para feedback de descartes.

Herméticos: keywords fijadas en un fixture (no dependen de config_local.py / CI).
"""
import pytest

import filters
from filters import clasificar_keywords


@pytest.fixture(autouse=True)
def _keywords_fijas(monkeypatch):
    monkeypatch.setattr(filters, "KEYWORDS_INCLUIR", ["box dental", "modulo", "container"])
    monkeypatch.setattr(filters, "KEYWORDS_EXCLUIR", ["modulo de capacitacion", "capacitacion"])
    monkeypatch.setattr(filters, "KEYWORDS_AMPLIO", [])


def test_incluir_y_excluir_marca_kw_excluir():
    # Matchea "modulo" (incluir) y "modulo de capacitacion" (excluir):
    # se cae en el filtro, y kw_excluir NO debe quedar vacío.
    incluye, kw_incluir, kw_excluir = clasificar_keywords(
        "Entrega de módulo de capacitación"
    )
    assert kw_excluir != []
    assert kw_incluir != []  # igual matcheó una de incluir
    assert incluye is False


def test_box_dentales_incluye_sin_exclusion():
    incluye, kw_incluir, kw_excluir = clasificar_keywords("Arriendo de box dentales")
    assert incluye is True
    assert kw_excluir == []
    assert "box dental" in kw_incluir
