"""
capac_score.py — Capa C aplicada al score: lee las bases (vía capa_c) y actualiza el score.

  estimar(codigo)  -> estima tokens SIN llamar a la API (para confirmar costo antes de gastar).
  analizar(codigo) -> llama a la IA, extrae datos de las bases, recalibra COMPLEJIDAD (y suma el
                      techo de presupuesto a MARGEN, que sigue PENDIENTE hasta la cubicación de
                      Valentina), actualiza el score y cachea todo en `analisis_bases`.

Honestidad: el margen NO se vuelve "real" acá (eso necesita la cubicación); Capa C aporta
complejidad evaluada + el techo de presupuesto. Todo queda en la trazabilidad.
"""
import re
import json
import datetime
import db
import scoring
import capa_c
import schema_v3


def _num(v):
    """La IA a veces devuelve dict/list/str donde se espera un número (ej. plazo/presupuesto).
    Coerce a int o None — así nunca se bindea un dict a SQLite (que lo rechaza)."""
    if isinstance(v, bool) or isinstance(v, (dict, list)):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        d = re.sub(r"\D", "", v)              # "336.469.000"/"60 días" → dígitos
        return int(d) if d else None
    return None


def _texto(v):
    """Coerce a texto para columnas TEXT: dict/list → JSON; None y str se mantienen."""
    if v is None or isinstance(v, str):
        return v
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def estimar(codigo):
    schema_v3.migrate()
    r = capa_c.analizar_bases(codigo=codigo, dry=True)
    if r.get("error"):
        return {"ok": False, "error": r["error"]}
    return {"ok": True, "tokens": r.get("tokens_estimados_entrada", 0), "meta": r.get("meta", [])}


def _complejidad(signals):
    n = len(signals or [])
    sc = 8 if n == 0 else 6 if n <= 2 else 4 if n <= 4 else 2
    if signals:
        nota = f"{n} señal(es) de complejidad: " + ", ".join(str(s) for s in signals[:3])
    else:
        nota = "sin señales de complejidad detectadas en las bases"
    return sc, nota


def analizar(codigo):
    schema_v3.migrate()
    res = capa_c.analizar_bases(codigo=codigo)
    if res.get("error"):
        return {"ok": False, "error": res["error"]}
    ex = res.get("extraccion") or {}
    if ex.get("_parse_error"):
        return {"ok": False, "error": "No se pudo interpretar la respuesta de la IA. Reintentá."}

    with db.conn() as c:
        row = c.execute("SELECT score_provisional, score_json FROM licitaciones WHERE codigo=?", (codigo,)).fetchone()
    if not row:
        return {"ok": False, "error": "Licitación no encontrada."}
    score_antes = row[0]
    sj = json.loads(row[1]) if row[1] else {"dimensiones": {}}
    dims = sj.get("dimensiones", {})

    signals = ex.get("señales_complejidad") or ex.get("senales_complejidad") or []
    csc, cnota = _complejidad(signals)
    dims["complejidad"] = {"score": csc, "nota": cnota, "evaluado": True}

    pres = _num(ex.get("presupuesto_clp"))     # la IA puede devolver dict/str: coerce a int o None
    if pres:
        pres_txt = f"${pres:,}".replace(",", ".")
        dims["margen"] = {"score": 5, "evaluado": False,
                          "nota": f"Techo de presupuesto {pres_txt} (Capa C). Falta costo/cubicación de Valentina para el margen."}

    sj["dimensiones"] = dims
    total = sum(dims[d]["score"] * scoring.PESOS[d] for d in scoring.PESOS if d in dims)
    sj["score_provisional"] = total
    sj["triage"] = scoring.triage(total)
    requiere = any(not dims[d].get("evaluado") for d in dims)
    sj["requiere_bases"] = requiere

    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db.conn() as c:
        db.set_score_provisional(c, codigo, total, json.dumps(sj, ensure_ascii=False), requiere)
        c.execute("""INSERT INTO analisis_bases
                     (codigo, ts, modelo, resumen, presupuesto_clp, plazo_dias, json_extraccion, score_antes, score_despues)
                     VALUES (?,?,?,?,?,?,?,?,?)""",
                  (codigo, ts, res.get("modelo"), _texto(ex.get("resumen")), pres,
                   _num(ex.get("plazo_entrega_dias")),
                   json.dumps(ex, ensure_ascii=False), score_antes, total))
        db.log_evento(c, codigo, "capa_c", f"Bases analizadas (Capa C). Score {score_antes}→{total}.")
    return {"ok": True, "score_antes": score_antes, "score_despues": total,
            "resumen": _texto(ex.get("resumen"))}
