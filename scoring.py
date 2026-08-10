"""
scoring.py — Scoring Atlas PROVISIONAL (paso 5a), solo con data de API.

Honestidad: NO inventa el margen. Las 6 dimensiones del framework Atlas:
  margen(×3), cashflow(×3), complejidad(×2), logístico(×2), alineación(×1), repetibilidad(×1)
De API se pueden estimar: LOGÍSTICO, ALINEACIÓN, REPETIBILIDAD y (parcial) CASHFLOW.
MARGEN y COMPLEJIDAD requieren bases + cubicación -> quedan en neutro (5) y se marcan.

Por eso el resultado es un SCORE PROVISIONAL para TRIAGE, no un GO/NO-GO.
El GO/NO-GO final lo da la Capa C cuando estén las bases y la cubicación de Valentina.

Umbrales de triage (sobre 120): >=85 Priorizar | >=60 Revisar | <60 Descartar candidato.
(El GO fuerte/мitigación del framework aplica al score FINAL, no al provisional.)
"""
import json

from textnorm import region_corta as _region_corta  # normalización compartida (una sola fuente)

PESOS = {"margen": 3, "cashflow": 3, "complejidad": 2, "logistico": 2, "alineacion": 1, "repetibilidad": 1}


def triage(total):
    """Umbral de triage sobre 120: >=85 Priorizar · >=60 Revisar · <60 Descartar candidato.
    Fuente única (la usan scoring, capac_score y cubicacion_ia)."""
    return "Priorizar" if total >= 85 else "Revisar" if total >= 60 else "Descartar candidato"

# Modalidad de pago — catálogo oficial ChileCompra (campo `Modalidad`, no `TipoPago`).
MODALIDAD_LABEL = {
    1: "Pago a 30 días", 2: "Pago a 30/60/90 días", 3: "Pago al día", 4: "Pago anual",
    5: "Pago bimensual", 6: "Pago contra entrega conforme", 7: "Pagos mensuales",
    8: "Pago por estado de avance", 9: "Pago trimestral", 10: "Pago a 60 días",
}
# Tier de cash flow por modalidad (1=mejor flujo … 3=peor). Usa la calibración del negocio si existe.
try:
    from config import CASHFLOW_TIER
except Exception:
    CASHFLOW_TIER = {3: 1, 6: 1, 1: 1, 10: 2, 2: 2, 8: 2, 7: 2, 5: 3, 9: 3, 4: 3}
_CF_SCORE = {1: 8, 2: 6, 3: 3}  # tier -> puntaje 0-10

# --- Distancia aprox. por carretera (km) desde cada base. CALIBRAR con datos reales. ---
# Se evalúa contra la base más cercana (estrategia dual-base Pirque + Puerto Montt).
BASES = {
    "Pirque": {  # Santiago RM
        "metropolitana": 30, "valparaíso": 120, "valparaiso": 120, "o'higgins": 90, "ohiggins": 90,
        "maule": 250, "ñuble": 400, "nuble": 400, "biobío": 500, "biobio": 500,
        "araucanía": 680, "araucania": 680, "los ríos": 850, "los rios": 850,
        "los lagos": 1000, "aysén": 1600, "aysen": 1600, "magallanes": 3000,
        "coquimbo": 470, "atacama": 800, "antofagasta": 1300, "tarapacá": 1800, "tarapaca": 1800,
        "arica": 2050, "parinacota": 2050,
    },
    "Puerto Montt": {  # Los Lagos (activa desde 1-ago-2026)
        "los lagos": 30, "los ríos": 200, "los rios": 200, "araucanía": 350, "araucania": 350,
        "aysén": 600, "aysen": 600, "biobío": 550, "biobio": 550, "ñuble": 650, "nuble": 650,
        "maule": 800, "metropolitana": 1000, "magallanes": 1400,
        "valparaíso": 1120, "valparaiso": 1120, "o'higgins": 950, "ohiggins": 950,
    },
}
# Calibración real opcional desde config_local.py (BASES_DISTANCIAS, misma estructura
# {base: {region_norm: km}}). Si no está, quedan las aproximaciones de arriba.
try:
    from config import BASES_DISTANCIAS as _BASES_CFG
    if _BASES_CFG:
        BASES = _BASES_CFG
except (ImportError, AttributeError):
    pass

PRODUCTOS_CORE = ["container", "conteiner", "contenedor", "box dental", "box veterinari",
                  "módulo", "modulo", "modular", "baño modular", "baños modulares",
                  "sala", "reas", "respel", "suspel"]
PERIFERICOS = ["paradero", "garita", "panel solar", "paneles solares", "carpa"]
ONE_OFF = ["mejoramiento", "remodelación", "remodelacion", "mantención", "mantencion",
           "habilitación", "habilitacion", "reparación", "reparacion", "ampliación", "ampliacion"]


# Nombre interno de config (pirque / puerto_montt) → clave de la tabla BASES de arriba.
_ALIAS_BASE = {"pirque": "Pirque", "puerto_montt": "Puerto Montt", "puertomontt": "Puerto Montt"}


def _base_activa():
    """La base desde la que se mide el traslado. Instrucción de Martín (ago-2026): SIEMPRE desde
    Pirque hasta nuevo aviso.

    Antes esto tomaba la base MÁS CERCANA de las dos, que es una operación distinta: suponía que
    el módulo puede salir indistintamente de Pirque o de Puerto Montt. Mientras la fabricación
    esté en un solo lugar, medir contra la más cercana subestima el flete — y el flete es la
    partida que más varía entre una licitación cerca y una lejos."""
    try:
        from config import BASE_OPERATIVA
        return _ALIAS_BASE.get(str(BASE_OPERATIVA).strip().lower())
    except Exception:
        return None


def _dist_min(region, base=None):
    """(km, base). Mide contra la base ACTIVA; sólo si no hay una configurada cae al mínimo
    entre todas, que es el comportamiento viejo."""
    if not region:
        return None, None
    r = region.lower()
    activa = base or _base_activa()
    candidatas = ({activa: BASES[activa]} if activa in BASES else BASES)
    best = None; base_n = None
    for bname, mp in candidatas.items():
        for key, km in mp.items():
            if key in r:
                if best is None or km < best:
                    best, base_n = km, bname
                break
    return best, base_n


def _logistico(region, comuna=None):
    km, base = _dist_min(region)
    lugar = ", ".join(x for x in [comuna, _region_corta(region)] if x) or (region or "—")
    if km is None:
        return 5, f"{lugar}: distancia no determinada (región sin mapear)", False
    trigger = km > 300
    if km <= 100:   sc = 9
    elif km <= 300: sc = 7
    elif km <= 600: sc = 4
    elif km <= 1000: sc = 2
    else:           sc = 1
    nota = f"{lugar}: ~{km} km de {base} (aprox., calibrar)"
    if trigger:
        nota += "  ·  ×3 logístico DISPARADO (>300 km)"
    return sc, nota, trigger


def _alineacion(nombre):
    n = nombre.lower()
    for k in PRODUCTOS_CORE:
        if k in n:
            return 9, f'producto core de Loveo (match: "{k}")'
    for k in PERIFERICOS:
        if k in n:
            return 6, f'periférico, capacidad parcial (match: "{k}")'
    return 4, "territorio nuevo (no matchea core ni periférico)"


def _repetibilidad(nombre):
    n = nombre.lower()
    modular = next((k for k in ["container", "contenedor", "box", "módulo", "modulo", "modular"] if k in n), None)
    oneoff = next((k for k in ONE_OFF if k in n), None)
    if modular and not oneoff:
        return 8, f'diseño replicable, modular estándar (match: "{modular}")'
    if oneoff:
        return 3, f'obra a medida, poco replicable (match: "{oneoff}")'
    return 5, "replicabilidad media (sin señales claras)"


def _cashflow(lic):
    mod = lic.get("modalidad")
    try:
        mod = int(mod) if mod is not None and str(mod).strip() != "" else None
    except (ValueError, TypeError):
        mod = None
    if mod is None:
        return 5, "modalidad de pago no informada por la API", True
    label = MODALIDAD_LABEL.get(mod, f"modalidad {mod}")
    tier = CASHFLOW_TIER.get(mod, 2)
    return _CF_SCORE.get(tier, 5), f"{label} — tier {tier} de cash flow", False


def score_provisional(lic: dict) -> dict:
    dims = {}
    log_sc, log_n, trig = _logistico(lic.get("region"), lic.get("comuna"))
    ali_sc, ali_n = _alineacion(lic.get("nombre") or "")
    rep_sc, rep_n = _repetibilidad(lic.get("nombre") or "")
    cf_sc, cf_n, cf_flag = _cashflow(lic)

    dims["logistico"]     = {"score": log_sc, "nota": log_n, "evaluado": True}
    dims["alineacion"]    = {"score": ali_sc, "nota": ali_n, "evaluado": True}
    dims["repetibilidad"] = {"score": rep_sc, "nota": rep_n, "evaluado": True}
    dims["cashflow"]      = {"score": cf_sc, "nota": cf_n, "evaluado": not cf_flag}
    dims["margen"]        = {"score": 5, "nota": "No evaluable con datos de API. Lo completan la Capa C (specs + cubicación tipo) y la cubicación de Valentina.", "evaluado": False}
    dims["complejidad"]   = {"score": 5, "nota": "No evaluable con datos de API. Requiere leer las bases técnicas (Capa C).", "evaluado": False}

    total = sum(dims[d]["score"] * PESOS[d] for d in PESOS)
    evaluado_pts = sum(PESOS[d] for d in PESOS if dims[d]["evaluado"]) * 10
    requiere_bases = any(not dims[d]["evaluado"] for d in dims)

    return {
        "score_provisional": total,
        "max": 120,
        "evaluable_pts": evaluado_pts,
        "triage": triage(total),
        "logistico_x3": trig,
        "requiere_bases": requiere_bases,
        "dimensiones": dims,
        "nota": "Score PROVISIONAL (API). Margen y complejidad pendientes de bases/cubicación. No es GO/NO-GO.",
    }


if __name__ == "__main__":
    import sys
    d = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "detalle.json"))["Listado"][0]
    from discover import _aplanar_detalle
    print(json.dumps(score_provisional(_aplanar_detalle(d)), indent=2, ensure_ascii=False))
