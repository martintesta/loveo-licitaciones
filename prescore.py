"""
prescore.py — pre-score de TRIAGE (honesto).

Con la sola API solo se puede puntuar de forma defendible:
  - cash flow  (modalidad de pago)        -> CASHFLOW_TIER
  - logística  (región vs. base operativa)-> LOGISTICA_TIER
  - alineación (fuerza de keywords)        -> cantidad de keywords que matchean

NO se inventan margen, complejidad ni repetibilidad: eso requiere los documentos
(bases/anexos) y se delega al scoring completo (Capa B, futura).

Etiqueta de triage (tiers: 1 = mejor):
  suma <= 4  -> PRIORITARIA
  suma <= 6  -> REVISAR
  suma  > 6  -> BAJA-PRIORIDAD
  sin región sur -> FUERA-DE-ZONA
"""
from config import LOGISTICA_TIER, CASHFLOW_TIER, BASE_OPERATIVA
from filters import region_sur, keywords_que_matchean

NOTA = (
    "PRE-SCORE de triage (Capa A). Solo puntúa cash flow, logística y alineación "
    "de keywords — lo único defendible con la API. NO incluye margen, complejidad "
    "ni repetibilidad: eso requiere los documentos (bases/anexos) y se delega al "
    "scoring completo (Capa B, futura). No es el scoring final."
)


def _tier_logistica(region_key):
    """Tier de logística desde la base operativa hacia la región sur dada."""
    return LOGISTICA_TIER.get(BASE_OPERATIVA, {}).get(region_key)


def _codigo_pago(detalle):
    """Código de modalidad de pago como int, o None si no se puede leer."""
    val = detalle.get("Modalidad", detalle.get("FormaPago"))
    try:
        return int(str(val).strip())
    except (TypeError, ValueError):
        return None


def _tier_cashflow(detalle):
    """(tier, codigo). Modalidad desconocida -> tier 3 (conservador)."""
    cod = _codigo_pago(detalle)
    if cod is None:
        return 3, None
    return CASHFLOW_TIER.get(cod, 3), cod


def _tier_alineacion(nombre):
    """(tier, n_keywords). Más keywords = mejor alineación (tier menor)."""
    n = len(keywords_que_matchean(nombre))
    if n >= 2:
        return 1, n
    if n == 1:
        return 2, n
    return 3, n


def prescore(detalle):
    """Devuelve un dict de triage para una licitación (su detalle)."""
    comprador = detalle.get("Comprador") or {}
    region_unidad = comprador.get("RegionUnidad", "")
    nombre = detalle.get("Nombre", "")

    region_key = region_sur(region_unidad)
    tier_cash, cod_pago = _tier_cashflow(detalle)
    tier_alin, n_kw = _tier_alineacion(nombre)

    if region_key is None:
        etiqueta = "FUERA-DE-ZONA"
        suma = None
        tier_log = None
    else:
        tier_log = _tier_logistica(region_key)
        if tier_log is None:
            # Región sur pero no está en la tabla de esta base: conservador.
            tier_log = 3
        suma = tier_log + tier_cash + tier_alin
        if suma <= 4:
            etiqueta = "PRIORITARIA"
        elif suma <= 6:
            etiqueta = "REVISAR"
        else:
            etiqueta = "BAJA-PRIORIDAD"

    return {
        "etiqueta": etiqueta,
        "suma_tiers": suma,
        "tier_logistica": tier_log,
        "tier_cashflow": tier_cash,
        "tier_alineacion": tier_alin,
        "region_sur": region_key,
        "base_operativa": BASE_OPERATIVA,
        "codigo_pago": cod_pago,
        "keywords_match": keywords_que_matchean(nombre),
        "n_keywords": n_kw,
        "nota": NOTA,
    }
