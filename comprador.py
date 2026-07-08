"""
comprador.py — Reputación de pago por comprador (la señal de la Ficha Comprador, capturada a mano).

La Ficha Comprador de Mercado Público (comportamiento de pago real: ¿paga a tiempo?) está detrás
del WAF + CAPTCHA de www.mercadopublico.cl → no se puede automatizar de forma confiable ni desde
IP residencial. Pero esa señal es valiosa para el cash flow. Acá se captura A MANO: la operadora,
que sí pasa el CAPTCHA en su navegador, marca la reputación una vez por organismo. El worker
(worker.ficha_comprador) escribiría en esta MISMA tabla el día que se pueda scrapear (fuente).

Es PROACTIVA y complementaria al descarte 'mal_pagador' (que es reactivo, por licitación): acá se
marca el comprador una vez y aplica a TODAS sus licitaciones. No toca el score numérico (eso lo
hace el descarte, deliberado por licitación) — se muestra como flag + alerta para no doblar la
penalización.

  set_reputacion(organismo, nivel, nota, fuente) -> upsert por organismo
  reputaciones()                                 -> {organismo: {nivel, nota, fuente}}
  alerta_para(rep)                               -> texto de alerta si nivel malo, si no None
"""
import db
import schema_v3

NIVELES = ("buena", "regular", "mala")
NIVEL_LABEL = {"buena": "Paga bien", "regular": "Pago irregular", "mala": "Mal pagador"}


def set_reputacion(organismo, nivel, nota="", fuente="manual"):
    """Upsert de la reputación de un comprador. nivel ∈ NIVELES."""
    if not organismo or not str(organismo).strip():
        raise ValueError("organismo vacío")
    if nivel not in NIVELES:
        raise ValueError(f"nivel inválido: {nivel} (esperado {NIVELES})")
    schema_v3.migrate()
    org = str(organismo).strip()
    now = db._now()
    with db.conn() as c:
        existe = c.execute("SELECT 1 FROM reputacion_comprador WHERE organismo=?", (org,)).fetchone()
        if existe:
            c.execute("UPDATE reputacion_comprador SET nivel=?, nota=?, fuente=?, ts=? WHERE organismo=?",
                      (nivel, nota, fuente, now, org))
        else:
            c.execute("INSERT INTO reputacion_comprador (organismo, nivel, nota, fuente, ts) "
                      "VALUES (?,?,?,?,?)", (org, nivel, nota, fuente, now))
    return nivel


def reputaciones():
    """Todas las reputaciones cargadas, {organismo: {nivel, nota, fuente}} (una lectura)."""
    schema_v3.migrate()
    with db.conn() as c:
        return {r["organismo"]: {"nivel": r["nivel"], "nota": r["nota"], "fuente": r["fuente"]}
                for r in c.execute("SELECT organismo, nivel, nota, fuente FROM reputacion_comprador").fetchall()}


def alerta_para(rep):
    """Texto de alerta si la reputación es mala; None si no hay reputación o es buena/regular."""
    if not rep:
        return None
    if rep.get("nivel") == "mala":
        base = "Comprador marcado MAL PAGADOR — revisá el cash flow"
        return f"{base}: {rep['nota']}" if rep.get("nota") else base + "."
    return None
