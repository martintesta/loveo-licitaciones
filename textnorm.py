"""
textnorm.py — Normalización de texto compartida (una sola fuente de verdad).

Antes, `_na` (sin acentos + minúsculas) y `_pat` (patrón de keyword: límite de palabra + plural
s/es) estaban copiados en ~8 módulos. Que discover y recall tuvieran COPIAS de `_pat` fue justo
lo que dejó pasar el bug de paridad de la auditoría de recall (una divergía de la otra). Acá viven
una sola vez.

  na(s)     -> str sin acentos, en minúsculas (fold ASCII).
  pat(term) -> regex compilada que matchea `term` con \b a la izquierda y plural s/es opcional.

Nota: cubicacion._na es DISTINTA a propósito (envuelve str() para números y hace .strip()); por eso
no delega acá. Si algún día se unifica, hacerlo con un test que fije ese comportamiento.
"""
import functools
import re
import unicodedata


def na(s):
    """Sin acentos (NFKD → fold ASCII) y en minúsculas. Cadena vacía si s es None."""
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


# Ordenados por longitud DESC para que el prefijo más específico gane ('Región de la ' antes que
# 'Región de '). Se ordena en runtime → agregar prefijos nuevos no rompe el orden.
_PREFIJOS_REGION = tuple(sorted(
    ("Región de la ", "Región del ", "Región de ", "Región "), key=len, reverse=True))


def region_corta(region):
    """Nombre de región sin el prefijo 'Región de/del/de la'. '' si es vacío. Ej.: 'Región del
    Maule' → 'Maule'. (tablero_data la envuelve con su propio fallback '—' para la UI.)"""
    if not region:
        return ""
    r = region.strip()
    for p in _PREFIJOS_REGION:
        if r.startswith(p):
            return r[len(p):]
    return r


@functools.lru_cache(maxsize=512)
def pat(term):
    """Regex de keyword: límite de palabra a la izquierda + plural s/es opcional + \b al final.

    Ej.: pat('modulo') matchea 'modulo', 'modulos', 'módulo', 'módulos'; el \b final evita que
    'box' matchee dentro de 'boxeo'. Cacheada: el set de términos es chico y se repiten en loops
    (kwstats.backfill, keywords.evaluar) — no recompilar la regex cada vez."""
    return re.compile(r"\b" + re.escape(na(term)) + r"(?:e?s)?\b")
