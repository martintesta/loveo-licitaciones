"""
rules.py — Admisibilidad (paso 3). Filtro eliminatorio Loveo a partir de la data de API.

Principios (anclados en calibración registrada y modelo Loveo):
  - NO rechazar por la mera presencia de ProhibicionContratacion: suele ser boilerplate.
    (issue de calibración #3 — rechazo demasiado agresivo). Solo se informa.
  - Loveo subcontrata soldadura/especialidades; si las bases PROHÍBEN subcontratar,
    es un riesgo real -> CONDICIONAL (no inadmisible automático, pero se marca fuerte).
  - Estados muertos (desierta/revocada/suspendida) -> inadmisible (no hay qué perseguir).
  - "Vigente para oferta" = estado publicada (5). Cerrada/adjudicada quedan para inteligencia.
  - Moneda != CLP o monto no usable -> admisible pero requiere bases para margen.

Devuelve dict: {admisible: bool, vigente: bool, motivos: [str], requiere_bases: bool}
"""

# Códigos de estado de Mercado Público (observados/típicos — CALIBRAR si aparecen otros)
ESTADO_PUBLICADA = 5
ESTADOS_MUERTOS = {7, 18, 19}   # 7 desierta, 18 revocada, 19 suspendida (típicos)

PROHIBE_SUBC_PAT = ["no se permite", "no permite", "prohíbe", "prohibe", "prohibida la subcontrat", "sin subcontrat"]


def evaluar(lic: dict) -> dict:
    motivos, admisible, requiere_bases = [], True, False
    estado = lic.get("estado_mp")
    vigente = (estado == ESTADO_PUBLICADA)

    # R1 — estado muerto
    if estado in ESTADOS_MUERTOS:
        admisible = False
        motivos.append(f"Estado MP {estado}: licitación no perseguible (desierta/revocada/suspendida)")
        return {"admisible": admisible, "vigente": False, "motivos": motivos, "requiere_bases": False}

    # R2 — subcontratación prohibida (riesgo real para el modelo Loveo)
    sub = (lic.get("subcontratacion") or "").lower()
    if any(p in sub for p in PROHIBE_SUBC_PAT):
        motivos.append("⚠ Las bases restringen subcontratación: Loveo depende de subcontratar soldadura/especialidades. Revisar BAE antes de ofertar")

    # R3 — moneda distinta de CLP
    moneda = (lic.get("moneda") or "CLP").upper()
    if moneda not in ("CLP", "PESO", "PESOS", ""):
        motivos.append(f"Moneda {moneda}: convertir antes de calcular margen")
        requiere_bases = True

    # R4 — monto no usable -> margen depende de bases/cubicación
    monto = lic.get("monto_estimado")
    if not monto or float(monto or 0) <= 0:
        motivos.append("MontoEstimado ausente/oculto: margen no evaluable sin bases")
        requiere_bases = True

    # R5 — ProhibicionContratacion: SOLO informativo (no eliminatorio)
    if (lic.get("prohibicion_subc") or "").strip():
        motivos.append("ℹ ProhibicionContratacion presente (boilerplate habitual; no eliminatorio)")

    if not motivos:
        motivos.append("Sin objeciones en metadata de API")

    return {"admisible": admisible, "vigente": vigente, "motivos": motivos, "requiere_bases": requiere_bases}


if __name__ == "__main__":
    import json, sys
    d = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "detalle.json"))["Listado"][0]
    from discover import _aplanar_detalle
    print(json.dumps(evaluar(_aplanar_detalle(d)), indent=2, ensure_ascii=False))
