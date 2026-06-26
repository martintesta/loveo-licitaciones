"""
aprendizaje.py — Aprende de los descartes para asistir el scoring (Fase 3).

Modo ASISTIDO y EXPLICABLE:
- Solo los descartes de tipo 'calidad' ATRIBUIBLES a un campo de la licitación generan ajuste:
    muy_lejos   -> por región
    mal_pagador -> por organismo (comprador)
  y SIEMPRE con su razón en texto. Umbral configurable (default 3 descartes parecidos).
- Los descartes 'operativo' (visita_perdida, sin_capacidad) NUNCA bajan el score (regla dura).
  visita_perdida genera una ALERTA ("perdiste N buenas por no ir a la visita"), no un castigo.

El ajuste es DISPLAY-ONLY: no muta score_provisional. Es reversible por naturaleza (sale de la
tabla `descartes`; si cambia el historial, cambia el ajuste).

  cargar()                          -> agrega los descartes una sola vez (para no consultar por lic)
  ajuste_lic(cargado, region, org)  -> {delta<=0, razones[], alertas[]}  (PURO, sin DB → testeable)
  resumen(cargado=None)             -> datos del panel "Aprendizaje"
"""
import db

UMBRAL = 3                                    # descartes parecidos para disparar el ajuste
PENAL = {"muy_lejos": 6, "mal_pagador": 8}    # cuánto baja cada patrón (sobre 120)


def cargar():
    """Lee los agregados de descartes UNA vez. Devuelve dicts {valor: conteo}."""
    reg, org, vis = {}, {}, {}
    with db.conn() as c:
        rows = c.execute("""
            SELECT d.categoria AS cat, l.region AS region, l.organismo AS organismo
            FROM descartes d JOIN licitaciones l ON l.codigo = d.codigo
            WHERE d.categoria IN ('muy_lejos', 'mal_pagador', 'visita_perdida')
        """).fetchall()
    for r in rows:
        cat = r["cat"]
        if cat == "muy_lejos" and r["region"]:
            reg[r["region"]] = reg.get(r["region"], 0) + 1
        elif cat == "mal_pagador" and r["organismo"]:
            org[r["organismo"]] = org.get(r["organismo"], 0) + 1
        elif cat == "visita_perdida" and r["organismo"]:
            vis[r["organismo"]] = vis.get(r["organismo"], 0) + 1
    return {"muy_lejos_region": reg, "mal_pagador_org": org, "visita_org": vis}


def ajuste_lic(cargado, region, organismo):
    """Ajuste asistido para UNA licitación. Puro (sin DB). delta<=0; razones y alertas explícitas."""
    delta, razones, alertas = 0, [], []
    n = cargado["muy_lejos_region"].get(region or "", 0)
    if n >= UMBRAL:
        delta -= PENAL["muy_lejos"]
        razones.append(f"-{PENAL['muy_lejos']}: descartaste {n} en {region} por 'muy lejos'")
    n = cargado["mal_pagador_org"].get(organismo or "", 0)
    if n >= UMBRAL:
        delta -= PENAL["mal_pagador"]
        razones.append(f"-{PENAL['mal_pagador']}: descartaste {n} de '{organismo}' por 'mal pagador'")
    nv = cargado["visita_org"].get(organismo or "", 0)
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
        "muy_lejos_region": _top(cargado["muy_lejos_region"]),
        "mal_pagador_org": _top(cargado["mal_pagador_org"]),
        "buenas_perdidas": sum(cargado["visita_org"].values()),
        "umbral": UMBRAL,
    }
