"""
filters.py — filtros del embudo: keywords, región sur y admisibilidad.

Matching de keywords por LÍMITE DE PALABRA a la izquierda (no substring crudo):
así `reas` NO matchea dentro de `áreas`, pero `box dental` SÍ matchea `box
dentales` y `prefabricad` SÍ matchea `prefabricado`. Ver nota abajo en `_matchea`.
"""
import re
import unicodedata

from config import KEYWORDS_INCLUIR, KEYWORDS_EXCLUIR, REGIONES_SUR


def _norm(s):
    """minúsculas + sin acentos (NFKD), para comparar de forma robusta."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def _matchea(kw, texto_norm):
    r"""True si `kw` aparece en `texto_norm` con límite de palabra a la izquierda.

    Se usa `\b` SOLO al inicio (no al final). Esto cumple las tres condiciones
    a la vez:
      - `reas`        NO matchea dentro de `areas`  (no hay \b antes de la 'r')
      - `box dental`  SÍ matchea `box dentales`     (la kw es prefijo de palabra)
      - `prefabricad` SÍ matchea `prefabricado`     (raíz/stem deliberada)

    (Un `\b` también al final rompería los dos últimos casos, que son tests
    explícitos del spec.)
    """
    return re.search(r"\b" + re.escape(_norm(kw)), texto_norm) is not None


def clasificar_keywords(nombre):
    """Clasifica el nombre contra las listas de keywords.

    Devuelve (incluye, kw_incluir, kw_excluir):
      - kw_incluir: keywords de INCLUIR que matchean.
      - kw_excluir: keywords de EXCLUIR que matchean.
      - incluye: True si matchea alguna de INCLUIR y NINGUNA de EXCLUIR
        (misma lógica que `pasa_keywords`).

    Permite distinguir, en el embudo, las que se caen por exclusión (matchearon
    incluir Y excluir) de las que simplemente no son relevantes.
    """
    t = _norm(nombre)
    kw_incluir = [kw for kw in KEYWORDS_INCLUIR if _matchea(kw, t)]
    kw_excluir = [kw for kw in KEYWORDS_EXCLUIR if _matchea(kw, t)]
    incluye = bool(kw_incluir) and not kw_excluir
    return incluye, kw_incluir, kw_excluir


def pasa_keywords(nombre):
    """True si el nombre matchea alguna keyword de INCLUIR y ninguna de EXCLUIR."""
    incluye, _, _ = clasificar_keywords(nombre)
    return incluye


def keywords_que_matchean(nombre):
    """Lista de keywords de INCLUIR que matchean el nombre (para alineación)."""
    t = _norm(nombre)
    return [kw for kw in KEYWORDS_INCLUIR if _matchea(kw, t)]


def region_sur(region_unidad):
    """Devuelve la clave de REGIONES_SUR que matchea (substring normalizado) o None."""
    r = _norm(region_unidad)
    if not r:
        return None
    for clave in REGIONES_SUR:
        if _norm(clave) in r:
            return clave
    return None


def admisibilidad(detalle):
    """Evalúa admisibilidad. Devuelve (es_admisible, motivos).

    El ÚNICO chequeo eliminatorio confiable con la API es SubContratacion == 0
    (Loveo depende de subcontratar soldadura/especialidades). `ProhibicionContratacion`
    NO es NO-GO automático (suele ser boilerplate de no-cesión): se expone como
    bandera informativa, no como rechazo.
    """
    motivos = []
    es_admisible = True

    subcon = str(detalle.get("SubContratacion", "")).strip()
    if subcon == "0":
        es_admisible = False
        motivos.append(
            "NO-GO: no permite subcontratación (SubContratacion=0); Loveo depende "
            "de subcontratar soldadura/especialidades."
        )

    prohibicion = detalle.get("ProhibicionContratacion")
    prohibicion_txt = str(prohibicion).strip() if prohibicion is not None else ""
    if prohibicion_txt and prohibicion_txt != "0":
        motivos.append(
            "BANDERA (informativa, no rechazo): ProhibicionContratacion presente; "
            "revisar — suele ser boilerplate de no-cesión."
        )

    return es_admisible, motivos
