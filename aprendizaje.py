"""
aprendizaje.py — Aprende de los descartes para asistir el scoring (Fase 3).

Modo ASISTIDO y EXPLICABLE. Solo los descartes de tipo 'calidad' ATRIBUIBLES a un campo
de la licitación generan ajuste, y SIEMPRE con su razón:
    muy_lejos            -> por región
    mal_pagador          -> por organismo (comprador)
    requisito_excluyente -> por organismo (si un comprador siempre exige lo que no podés)

Categorías de calidad SIN señal atribuible desde la API (margen_bajo, fuera_de_core,
muy_complejo): NO ajustan el score; solo aparecen en el panel por categoría. Honesto: no se
inventa un patrón donde la data de API no lo permite (el margen necesita cubicación, etc.).

Los descartes 'operativo' (visita_perdida, sin_capacidad) NUNCA bajan el score. visita_perdida
genera una ALERTA ("perdiste N buenas por no ir a la visita").

El ajuste es DISPLAY-ONLY (no muta score_provisional): reversible por naturaleza.

Calibración: UMBRAL y PENAL se pueden sobreescribir desde config (config_local.py); si no están,
caen a los defaults de acá.

  cargar()                          -> agrega los descartes una sola vez (no consulta por lic)
  ajuste_lic(cargado, region, org)  -> {delta<=0, razones[], alertas[]}  (PURO, sin DB → testeable)
  resumen(cargado=None)             -> datos del panel "Aprendizaje"
"""
import db

# Calibración (sobreescribible desde config_local.py). Defaults conservadores.
try:
    from config import APRENDIZAJE_UMBRAL as UMBRAL
except (ImportError, AttributeError):
    UMBRAL = 3                                    # descartes parecidos para disparar el ajuste
try:
    from config import APRENDIZAJE_PENAL as PENAL
except (ImportError, AttributeError):
    PENAL = {"muy_lejos": 6, "mal_pagador": 8, "requisito_excluyente": 8}  # baja sobre 120


def cargar():
    """Lee los agregados de descartes UNA vez. {valor: conteo} por categoría atribuible + visita."""
    reg, org_pago, org_req, vis = {}, {}, {}, {}
    with db.conn() as c:
        rows = c.execute("""
            SELECT d.categoria AS cat, l.region AS region, l.organismo AS organismo
            FROM descartes d JOIN licitaciones l ON l.codigo = d.codigo
            WHERE d.categoria IN ('muy_lejos', 'mal_pagador', 'requisito_excluyente', 'visita_perdida')
        """).fetchall()
    for r in rows:
        cat, region, org = r["cat"], r["region"], r["organismo"]
        if cat == "muy_lejos" and region:
            reg[region] = reg.get(region, 0) + 1
        elif cat == "mal_pagador" and org:
            org_pago[org] = org_pago.get(org, 0) + 1
        elif cat == "requisito_excluyente" and org:
            org_req[org] = org_req.get(org, 0) + 1
        elif cat == "visita_perdida" and org:
            vis[org] = vis.get(org, 0) + 1
    return {"muy_lejos_region": reg, "mal_pagador_org": org_pago,
            "requisito_excluyente_org": org_req, "visita_org": vis}


def ajuste_lic(cargado, region, organismo):
    """Ajuste asistido para UNA lic. Puro (sin DB). delta<=0; razones y alertas explícitas."""
    delta, razones, alertas = 0, [], []
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
        rows = c.execute("""SELECT categoria, tipo, COUNT(*) AS n FROM descartes
                            WHERE categoria IS NOT NULL
                            GROUP BY categoria, tipo ORDER BY n DESC""").fetchall()
    for r in rows:
        por_cat.append({"categoria": r["categoria"], "tipo": r["tipo"], "n": r["n"]})

    def _top(d):
        return sorted(({"k": k, "n": v} for k, v in d.items()), key=lambda x: x["n"], reverse=True)

    return {
        "por_categoria": por_cat,
        "muy_lejos_region": _top(cargado.get("muy_lejos_region", {})),
        "mal_pagador_org": _top(cargado.get("mal_pagador_org", {})),
        "requisito_excluyente_org": _top(cargado.get("requisito_excluyente_org", {})),
        "buenas_perdidas": sum(cargado.get("visita_org", {}).values()),
        "umbral": UMBRAL,
    }
