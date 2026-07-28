"""
plan.py — Motor "Plan del día" / próxima mejor acción (epic plan-del-dia, Fase 1).

Compone las señales que ya arma build_data (score × confianza, días al cierre, visita obligatoria,
estado en el embudo, si falta la cubicación, análisis de bases) en una COLA PRIORIZADA DE ACCIONES,
cada una con su porqué. Puro (lics → acciones), sin DB: el usuario ve QUÉ HACER PRIMERO sin tener
que decidirlo él. Es una sugerencia; no ejecuta nada.

  construir(lics, hoy=None, limite=12) -> [{tipo, codigo, titulo, motivo, prioridad, dias}] ordenada
"""

# Pesos/umbrales (sobreescribibles desde config_local.py). La prioridad de cada acción es
#   valor (score×confianza) + urgencia (por deadline) + tipo (los atados a deadline arriba).
try:
    from config import PLAN_UMBRAL_CIERRE as UMBRAL_CIERRE
except (ImportError, AttributeError):
    UMBRAL_CIERRE = 10          # días: mirar cierres dentro de esta ventana
try:
    from config import PLAN_UMBRAL_VISITA as UMBRAL_VISITA
except (ImportError, AttributeError):
    UMBRAL_VISITA = 14          # días: mirar visitas dentro de esta ventana
try:
    from config import PLAN_PESO_URGENCIA as PESO_URGENCIA
except (ImportError, AttributeError):
    PESO_URGENCIA = 60          # cuánto suma la cercanía del deadline (máximo)
try:
    from config import PLAN_TIPO_BOOST as TIPO_BOOST
except (ImportError, AttributeError):
    TIPO_BOOST = {"VISITA": 45, "PRESENTAR": 35, "CIERRE": 22, "CUBICAR": 15, "REVISAR": 6, "BASES": 6}

_ESTRES = {  # etiqueta corta por tipo (para la UI)
    "VISITA": "Visita", "PRESENTAR": "Presentar", "CIERRE": "Cierre", "CUBICAR": "Cubicar",
    "REVISAR": "Revisar", "BASES": "Bases",
}


def _activa(l):
    """En juego: ni descartada, ni ya presentada/cerrada, ni con el cierre ya pasado."""
    if l.get("dias") is not None and l.get("dias") < 0:
        return False                                     # el cierre ya pasó: no hay nada que hacer
    return l.get("estRev") != "descartada" and (l.get("estRes") in (None, "", "pendiente"))


def _valor(l):
    """Valor de la lic: score ponderado por su confianza (dimensiones con dato real)."""
    sc = l.get("score")
    if sc is None:
        return 0.0
    nd = l.get("nDims") or 6
    ev = l.get("evDims")
    conf = (ev / nd) if (ev is not None and nd) else 0.5
    return sc * conf


def _urgencia(dias, umbral):
    """0..PESO_URGENCIA: cuanto más cerca el deadline, más urgente. None si no aplica."""
    if dias is None or dias < 0 or dias > umbral:
        return None
    return round(PESO_URGENCIA * (umbral - dias) / umbral, 1)


def _tiene_bases(l):
    return bool(l.get("analisis"))


def _margen_hecho(l):
    """El margen ya está evaluado (la dimensión margen del score dejó de ser neutro)."""
    for d in (l.get("dims") or []):
        if d.get("n", "").lower().startswith("marg"):
            return bool(d.get("ev"))
    return False


def _accion_de(l):
    """La ÚNICA acción más pertinente para una lic (o None). Precedencia: visita > cierre > revisar."""
    cod, nom = l.get("cod"), (l.get("nom") or "—")
    dv, dc = l.get("diasVisita"), l.get("dias")
    sc = l.get("score")

    uv = _urgencia(dv, UMBRAL_VISITA)
    if uv is not None:                                   # visita obligatoria próxima → lo más crítico
        cuando = "HOY" if dv == 0 else "mañana" if dv == 1 else f"en {dv} días"
        return _mk("VISITA", cod, nom, f"Visita a terreno {cuando} — agendala/andá (si la perdés, "
                   f"quedás afuera).", l, uv, dv)

    uc = _urgencia(dc, UMBRAL_CIERRE)
    if uc is not None:                                   # cierra pronto → según en qué punto está
        cuando = "HOY" if dc == 0 else "mañana" if dc == 1 else f"en {dc} días"
        if l.get("estRev") == "aprobada":
            return _mk("PRESENTAR", cod, nom, f"Aprobada y cierra {cuando} — preparala y presentá.", l, uc, dc)
        if _tiene_bases(l) and not _margen_hecho(l):
            return _mk("CUBICAR", cod, nom, f"Cierra {cuando} y falta la cubicación — cargala para el "
                       f"GO/NO-GO.", l, uc, dc)
        if l.get("estRev") == "nueva":
            return _mk("REVISAR", cod, nom, f"Cierra {cuando} y todavía sin revisar — decidí ya.", l, uc, dc)
        return _mk("CIERRE", cod, nom, f"En juego y cierra {cuando}.", l, uc, dc)

    # Sin deadline inmediato: nuevas fit valiosas para triage, o cubicación pendiente.
    if l.get("estRev") == "nueva" and l.get("tri") in ("Priorizar", "Revisar"):
        return _mk("REVISAR", cod, nom, f"Nueva fit sin revisar (score {sc}) — revisá para decidir.", l, None, dc)
    if l.get("estRev") in ("en_revision", "aprobada") and _tiene_bases(l) and not _margen_hecho(l):
        return _mk("CUBICAR", cod, nom, "Bases leídas, falta la cubicación para cerrar el margen.", l, None, dc)
    if l.get("estRev") in ("en_revision", "aprobada") and not _tiene_bases(l) and l.get("tri") in ("Priorizar", "Revisar"):
        return _mk("BASES", cod, nom, f"La seguís (score {sc}) pero sin bases analizadas — conseguí las "
                   f"bases (Drive) para poder decidir.", l, None, dc)
    return None


def _mk(tipo, cod, nom, motivo, l, urgencia, dias):
    prioridad = round(_valor(l) + (urgencia or 0) + TIPO_BOOST.get(tipo, 0), 1)
    return {"tipo": tipo, "etiqueta": _ESTRES[tipo], "codigo": cod, "titulo": nom,
            "motivo": motivo, "prioridad": prioridad, "dias": dias,
            "score": l.get("score"), "regc": l.get("regc"), "org": l.get("org")}


def construir(lics, hoy=None, limite=12):
    """Cola priorizada de acciones a partir del `lics` de build_data. hoy queda para la Fase 3
    (por ahora los días ya vienen calculados en las lics)."""
    acciones = []
    for l in (lics or {}).values():
        if not _activa(l):
            continue
        a = _accion_de(l)
        if a:
            acciones.append(a)
    acciones.sort(key=lambda a: a["prioridad"], reverse=True)
    return acciones[:limite]
