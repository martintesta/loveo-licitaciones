"""
alertas.py — M-2: alertas de deadline (cierre) y visita a terreno.

Las fechas confiables viven en el bloque `Fechas` del detalle: el `FechaCierre`
de primer nivel a veces viene en None, pero `Fechas.FechaCierre` está poblado.
El campo de visita a terreno es `Fechas.FechaVisitaTerreno` (verificado contra
la API en vivo).

Este módulo NO envía notificaciones. `alertas_pendientes(resultados)` devuelve
la lista lista para que una capa de notificación futura (email/WhatsApp) la
consuma; el canal de envío irá por env/secret, nunca hardcodeado.
"""
from datetime import datetime

import config


def _parse_fecha(valor):
    """Parsea fechas ISO de la API ('2026-06-22T16:00:00'). None si no se puede."""
    if not valor:
        return None
    try:
        # Tomar los primeros 19 chars descarta fracciones de segundo/zonas.
        return datetime.fromisoformat(str(valor).strip()[:19])
    except ValueError:
        return None


def fecha_cierre(detalle):
    """Fecha de cierre confiable: Fechas.FechaCierre, con fallback al top-level."""
    fechas = detalle.get("Fechas") or {}
    return fechas.get("FechaCierre") or detalle.get("FechaCierre")


def fecha_visita(detalle):
    """Fecha de visita a terreno (Fechas.FechaVisitaTerreno), o None."""
    fechas = detalle.get("Fechas") or {}
    return fechas.get("FechaVisitaTerreno")


def dias_hasta(fecha_valor, hoy=None):
    """Días enteros desde hoy hasta la fecha (negativo si ya pasó). None si no parsea."""
    f = _parse_fecha(fecha_valor)
    if f is None:
        return None
    hoy = hoy or datetime.now()
    return (f.date() - hoy.date()).days


def evaluar_alertas(detalle, hoy=None, umbral=None):
    """Calcula días y alertas de cierre y visita para un detalle de licitación.

    Devuelve dict con: fecha_cierre, dias_al_cierre, fecha_visita, dias_a_visita,
    alerta_cierre, alerta_visita. Una alerta se prende si la fecha es hoy o dentro
    de `umbral` días (0 <= dias <= umbral); fechas pasadas no alertan.
    """
    umbral = config.DIAS_ALERTA_CIERRE if umbral is None else umbral
    fc = fecha_cierre(detalle)
    fv = fecha_visita(detalle)
    d_cierre = dias_hasta(fc, hoy)
    d_visita = dias_hasta(fv, hoy)
    return {
        "fecha_cierre": fc or "",
        "dias_al_cierre": d_cierre,
        "fecha_visita": fv or "",
        "dias_a_visita": d_visita,
        "alerta_cierre": d_cierre is not None and 0 <= d_cierre <= umbral,
        "alerta_visita": d_visita is not None and 0 <= d_visita <= umbral,
    }


def alertas_pendientes(resultados):
    """Candidatas con alguna alerta activa, ordenadas por dias_al_cierre asc.

    Pensada para que una capa de notificación futura la consuma. NO envía nada.
    """
    pend = [r for r in resultados if r.get("alerta_cierre") or r.get("alerta_visita")]
    pend.sort(key=lambda r: r["dias_al_cierre"] if r.get("dias_al_cierre") is not None else 9999)
    return pend
