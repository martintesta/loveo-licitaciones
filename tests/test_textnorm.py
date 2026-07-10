"""
test_textnorm.py — Contrato de la normalización compartida (textnorm.na / textnorm.pat).

Fija el comportamiento que ~8 módulos (discover, recall, kwstats, keywords, bases, tablero_data…)
delegan acá. Que discover y recall tuvieran COPIAS de `pat` fue lo que dejó pasar el bug de
paridad de recall; este test evita que la única fuente drifte.

  python -m pytest tests/test_textnorm.py -q
"""
import textnorm


def test_na_saca_acentos_y_baja():
    assert textnorm.na("Módulo Baño") == "modulo bano"
    assert textnorm.na("ÁRTICO ñandú") == "artico nandu"


def test_na_none_es_vacio():
    assert textnorm.na(None) == ""


def test_pat_matchea_plural_y_acentos():
    p = textnorm.pat("modulo")
    for s in ("modulo", "modulos", "módulo", "módulos"):
        assert p.search(textnorm.na(s)), s
    p2 = textnorm.pat("container")
    assert p2.search(textnorm.na("containers"))


def test_pat_respeta_limite_de_palabra():
    # 'box' no debe matchear dentro de 'boxeo' (el \b final lo evita)
    assert textnorm.pat("box").search(textnorm.na("box dental"))
    assert not textnorm.pat("box").search(textnorm.na("boxeo profesional"))


def test_discover_y_recall_comparten_la_misma_fuente():
    """Regresión del bug de paridad: discover._pat y recall._pat deben SER textnorm.pat."""
    import discover
    import recall
    assert discover._pat is textnorm.pat
    assert recall._pat is textnorm.pat
    assert discover._na is textnorm.na is recall._na
