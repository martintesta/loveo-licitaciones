"""
test_vocabulario_coherente.py — Descubrimiento y embudo tienen que hablar el mismo idioma.

El bug que motiva este archivo: cuando Martín confirmó que la clínica dental móvil es core, los
tokens se agregaron a `triage.TOKENS_CORE` y ahí quedó. Pero **el embudo sólo ve lo que
descubrimiento ya dejó entrar**: `triage` puede rechazar, nunca rescatar. Con `clinica movil`
ausente de las keywords, el gate declaraba core un producto que jamás iba a llegarle.

Costó tres licitaciones medidas: 640840-10-LP26 (clínica dental móvil), 2661-35-LP26 (veterinaria
móvil de Natales) y 2381-54-LE26 (3 box clínicos). Una cuarta, 3713-8-LP26, entró de pura
casualidad: matcheó el término amplio "posta" porque el hospital se llama Posta Rural Quilimarí.

Ninguna de las dos listas es la fuente de verdad de la otra, así que la coherencia no se puede
garantizar por construcción — sólo se puede medir. Eso hace este test.

  python -m pytest tests/test_vocabulario_coherente.py -q
"""
import pytest

import triage
from textnorm import na as _na, pat as _pat

try:
    from config_local import KEYWORDS_INCLUIR, KEYWORDS_AMPLIO
except ImportError:                                     # entorno sin calibración privada
    pytest.skip("sin config_local: no hay vocabulario que auditar", allow_module_level=True)


_RX_DESCUBRIMIENTO = [_pat(k) for k in list(KEYWORDS_INCLUIR) + list(KEYWORDS_AMPLIO)]


def _descubrible(token):
    """¿Un título que contenga este token sobreviviría al filtro de descubrimiento?"""
    return any(rx.search(_na(token)) for rx in _RX_DESCUBRIMIENTO)


def test_todo_token_core_del_embudo_es_descubrible():
    """La invariante: si el embudo lo considera producto de Loveo, descubrimiento tiene que
    dejarlo entrar. Si no, el token es letra muerta — el gate nunca lo va a ver."""
    huerfanos = sorted({t for t in triage.TOKENS_CORE if not _descubrible(t)})
    assert not huerfanos, (
        "tokens core que descubrimiento NUNCA va a dejar entrar (agregalos a KEYWORDS_INCLUIR "
        f"en config_local.py y a la tabla `keywords`): {huerfanos}"
    )


@pytest.mark.parametrize("titulo", [
    "CLINICA DENTAL MOVIL",
    "ADQUISICION CLINICAS MOVILES",
    "ADQUISICIÓN CLINICA VETERINARIA MOVIL NATALES",
    "CONSTRUCCIÓN Y HABILITACIÓN DE 3 BOX CLÍNICOS",
    "HABILITACION DE BOX CLINICO",
])
def test_los_casos_que_se_perdieron_ahora_entran(titulo):
    """Regresión con los títulos reales de Mercado Público que el filtro dejaba pasar de largo."""
    import discover
    discover._PATRONES_CACHE = None
    assert discover.matchea(titulo), f"descubrimiento sigue sin pescar: {titulo}"


@pytest.mark.parametrize("titulo", [
    "Fabricación e instalación mobiliario Serpat",
    "SERVICIO DE REPARACIÓN CÁMARA FRIGORIFICA",
    "Adquisición de balanzas tallímetros caliper y cintas métricas",
    "VEHICULOS PARA LA MUNICIPALIDAD DE PARRAL",
])
def test_el_vocabulario_nuevo_no_arrastra_los_falsos_positivos(titulo):
    """Las cuatro que el score de 6 dimensiones puntuó 49-79 y el humano marcó falso positivo.
    Ampliar el vocabulario no puede costar esta precisión."""
    import discover
    discover._PATRONES_CACHE = None
    assert not discover.matchea(titulo), f"ahora entra basura: {titulo}"
