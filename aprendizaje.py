"""
aprendizaje.py — Aprende de descartes Y resultados para asistir el scoring (Fases 3 + B).

DESCARTES (calidad, atribuibles) — BAJAN el score:
    muy_lejos -> región · mal_pagador / requisito_excluyente -> comprador
RESULTADOS:
    victorias -> por región y comprador → SUBEN el score de parecidas
    pérdidas 'malfit' (requisito / plazo / "no era para nosotros") -> por comprador → BAJAN
    pérdidas 'competida' (precio / competencia) -> NO tocan el score (era buena, competiste)

Operativo (visita_perdida) nunca penaliza: genera ALERTA. El ajuste es DISPLAY-ONLY (no muta el
score base) → reversible. Calibración (UMBRAL / UMBRAL_RES / PENAL / BONUS) sobreescribible desde
config_local.py; si no, defaults de acá.

  cargar()                          -> agrega descartes + resultados una sola vez
  ajuste_lic(cargado, region, org)  -> {delta, razones[], alertas[]}  (PURO). delta puede ser + o -
  resumen(cargado=None)             -> datos del panel "Aprendizaje"
"""
import db

try:
    from config import APRENDIZAJE_UMBRAL as UMBRAL
except (ImportError, AttributeError):
    UMBRAL = 3                                    # descartes parecidos para disparar el ajuste
try:
    from config import APRENDIZAJE_UMBRAL_RESULTADO as UMBRAL_RES
except (ImportError, AttributeError):
    UMBRAL_RES = 2                                # resultados: más raros y fuertes que los descartes
try:
    from config import APRENDIZAJE_PENAL as PENAL
except (ImportError, AttributeError):
    PENAL = {"muy_lejos": 6, "mal_pagador": 8, "requisito_excluyente": 8, "malfit": 6}
try:
    from config import APRENDIZAJE_BONUS as BONUS
except (ImportError, AttributeError):
    BONUS = {"gana_region": 5, "gana_org": 6}    # cuánto SUBE una racha de victorias


def cargar():
    """Lee los agregados de descartes + resultados UNA vez. {valor: conteo} por eje."""
    reg, org_pago, org_req, vis = {}, {}, {}, {}
    gana_reg, gana_org, malfit_org = {}, {}, {}
    with db.conn() as c:
        for r in c.execute("""
            SELECT d.categoria AS cat, l.region AS region, l.organismo AS organismo
            FROM descartes d JOIN licitaciones l ON l.codigo = d.codigo
            WHERE d.categoria IN ('muy_lejos', 'mal_pagador', 'requisito_excluyente', 'visita_perdida')
        """).fetchall():
            cat, region, org = r["cat"], r["region"], r["organismo"]
            if cat == "muy_lejos" and region:
                reg[region] = reg.get(region, 0) + 1
            elif cat == "mal_pagador" and org:
                org_pago[org] = org_pago.get(org, 0) + 1
            elif cat == "requisito_excluyente" and org:
                org_req[org] = org_req.get(org, 0) + 1
            elif cat == "visita_perdida" and org:
                vis[org] = vis.get(org, 0) + 1
        for r in c.execute("""
            SELECT res.impacto AS impacto, l.region AS region, l.organismo AS organismo
            FROM resultados res JOIN licitaciones l ON l.codigo = res.codigo
            WHERE res.impacto IN ('positivo', 'malfit')
        """).fetchall():
            imp, region, org = r["impacto"], r["region"], r["organismo"]
            if imp == "positivo":
                if region:
                    gana_reg[region] = gana_reg.get(region, 0) + 1
                if org:
                    gana_org[org] = gana_org.get(org, 0) + 1
            elif imp == "malfit" and org:
                malfit_org[org] = malfit_org.get(org, 0) + 1
    return {"muy_lejos_region": reg, "mal_pagador_org": org_pago,
            "requisito_excluyente_org": org_req, "visita_org": vis,
            "gana_region": gana_reg, "gana_org": gana_org, "malfit_org": malfit_org}


def ajuste_lic(cargado, region, organismo):
    """Ajuste asistido para UNA lic. Puro. delta + (victorias) o - (descartes / malfit)."""
    delta, razones, alertas = 0, [], []
    # Descartes de calidad (bajan)
    n = cargado.get("muy_lejos_region", {}).get(region or "", 0)
    if n >= UMBRAL:
        delta -= PENAL["muy_lejos"]
        razones.append(f"-{PENAL['muy_lejos']}: descartaste {n} en {region} por 'muy lejos'")
    n = cargado.get("mal_pagador_org", {}).get(organismo or "", 0)
    if n >= UMBRAL:
        delta -= PENAL["mal_pagador"]
        razones.append(f"-{PENAL['mal_pagador']}: descartaste {n} de '{organismo}' por 'mal pagador'")
    n = cargado.get("requisito_excluyente_org", {}).get(organismo or "", 0)
    if n >= UMBRAL:
        delta -= PENAL["requisito_excluyente"]
        razones.append(f"-{PENAL['requisito_excluyente']}: descartaste {n} de '{organismo}' por 'requisito excluyente'")
    # Resultados: victorias (suben)
    n = cargado.get("gana_region", {}).get(region or "", 0)
    if n >= UMBRAL_RES:
        delta += BONUS["gana_region"]
        razones.append(f"+{BONUS['gana_region']}: ganaste {n} en {region}")
    n = cargado.get("gana_org", {}).get(organismo or "", 0)
    if n >= UMBRAL_RES:
        delta += BONUS["gana_org"]
        razones.append(f"+{BONUS['gana_org']}: ganaste {n} de '{organismo}'")
    # Resultados: pérdidas por mal fit (bajan). Las 'competida' NO entran acá (no tocan el score).
    n = cargado.get("malfit_org", {}).get(organismo or "", 0)
    if n >= UMBRAL_RES:
        delta -= PENAL.get("malfit", 6)
        razones.append(f"-{PENAL.get('malfit', 6)}: perdiste {n} de '{organismo}' por mal fit (requisito/plazo)")
    # Operativo: alerta, no penaliza
    nv = cargado.get("visita_org", {}).get(organismo or "", 0)
    if nv >= 1:
        alertas.append(f"Perdiste {nv} de '{organismo}' por no llegar a la visita (eran buenas)")
    return {"delta": delta, "razones": razones, "alertas": alertas}


def resumen(cargado=None):
    """Datos para el panel 'Aprendizaje'."""
    if cargado is None:
        cargado = cargar()
    por_cat = []
    with db.conn() as c:
        for r in c.execute("""SELECT categoria, tipo, COUNT(*) AS n FROM descartes
                              WHERE categoria IS NOT NULL
                              GROUP BY categoria, tipo ORDER BY n DESC""").fetchall():
            por_cat.append({"categoria": r["categoria"], "tipo": r["tipo"], "n": r["n"]})

    def _top(d):
        return sorted(({"k": k, "n": v} for k, v in d.items()), key=lambda x: x["n"], reverse=True)

    return {
        "por_categoria": por_cat,
        "muy_lejos_region": _top(cargado.get("muy_lejos_region", {})),
        "mal_pagador_org": _top(cargado.get("mal_pagador_org", {})),
        "requisito_excluyente_org": _top(cargado.get("requisito_excluyente_org", {})),
        "gana_region": _top(cargado.get("gana_region", {})),
        "gana_org": _top(cargado.get("gana_org", {})),
        "malfit_org": _top(cargado.get("malfit_org", {})),
        "buenas_perdidas": sum(cargado.get("visita_org", {}).values()),
        "umbral": UMBRAL,
    }
