"""Tests de M-1: clasificación de keywords para feedback de descartes."""
from filters import clasificar_keywords


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
