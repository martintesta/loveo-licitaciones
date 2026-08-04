"""
test_bases.py — Sensor del recorte por secciones (lógica pura sobre texto, sin PDF).

bases.secciones() parte el texto por los encabezados típicos de las bases de MP. Es lo que
decide qué fragmentos se le mandan a la Capa C, así que conviene cubrirlo.

  python -m pytest tests/test_bases.py -q
"""
import bases


def test_secciones_detecta_encabezados_tipicos():
    texto = (
        "Antecedentes generales del llamado.\n"
        "El presupuesto disponible es de $50.000.000.\n"
        "El plazo de entrega es de 60 dias corridos.\n"
        "Se exige garantia de fiel cumplimiento del contrato.\n"
        "Criterios de evaluacion: precio 60%, experiencia 40%.\n"
    )
    secs = bases.secciones(texto)
    assert "presupuesto" in secs
    assert "plazo" in secs
    assert "garantias" in secs
    assert "evaluacion" in secs


def test_secciones_sin_encabezados_vacio():
    assert bases.secciones("texto sin nada que reconocer por aqui") == {}


def test_normalizar_con_mapa_apunta_al_original():
    """El mapa debe devolver, para cada char del normalizado, el índice ORIGINAL que lo produjo
    (bug de auditoría: se buscaba en normalizado y se recortaba el original → secciones corridas)."""
    t = 'Introducción • objeto — "proyecto" a 20°C … ñandú'
    n, mapa = bases._normalizar_con_mapa(t)
    assert n[:12] == "introduccion"                  # sin acentos y en minúsculas
    assert "ñ" not in n and "nandu" in n
    assert len(mapa) == len(n) + 1                   # +1 por el centinela de fin
    for i, ch in enumerate(n):                       # cada char apunta a su origen real
        assert mapa[i] < len(t)
    p = n.find("nandu")
    assert t[mapa[p]] == "ñ"                         # traduce de vuelta al char original


def test_secciones_con_ligadura_no_rompe_la_palabra():
    """Los PDFs traen ligaduras ('ﬁ'): al expandir NFKD ocupan 2 chars. Si se truncaban, quedaba
    'fnanciamiento' y la sección NO se detectaba."""
    t = "Antecedentes\nEl ﬁnanciamiento es municipal y cubre la obra completa."
    secs = bases.secciones(t)
    assert "presupuesto" in secs                     # antes: {} (no detectaba nada)
    assert "nanciamiento" in secs["presupuesto"]


def test_secciones_con_simbolos_recorta_en_el_lugar_correcto():
    """Regresión: con viñetas/dashes/comillas antes del encabezado, la sección arrancaba corrida
    (se buscaba sobre texto normalizado que BORRABA esos símbolos y se recortaba el original)."""
    texto = ('INTRODUCCIÓN • objeto — alcance del "proyecto" a 20°C … y más\n'
             'PRESUPUESTO disponible: 50.000.000 pesos\n'
             'PLAZO DE ENTREGA: 60 dias\n')
    secs = bases.secciones(texto)
    assert secs["presupuesto"].startswith("PRESUPUESTO disponible")   # antes: texto de la intro
    assert "50.000.000" in secs["presupuesto"]
    assert secs["plazo"].startswith("PLAZO DE ENTREGA")
