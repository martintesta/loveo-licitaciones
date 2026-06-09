"""Tests de M-3: red ancha de recall léxico."""
from filters import es_candidata_recall, keywords_amplio_que_matchean


def test_solo_amplio_cae_en_recall():
    # "posta" es término amplio y NO está en la lista estricta de INCLUIR.
    nombre = "Construcción posta rural Llanada Grande"
    assert keywords_amplio_que_matchean(nombre) != []
    assert es_candidata_recall(nombre) is True


def test_estricto_no_cae_en_recall():
    # "container" es keyword estricta -> va al output normal, NO a recall.
    nombre = "Adquisición de container para bodega municipal"
    assert es_candidata_recall(nombre) is False


def test_sin_match_no_cae_en_recall():
    assert es_candidata_recall("Servicio de aseo de oficinas") is False
