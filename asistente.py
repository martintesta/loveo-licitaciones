"""
asistente.py — Asistente IA Nivel 1: text-to-SQL (SOLO LECTURA) sobre loveo.db.

Pregunta en lenguaje natural → Claude genera un SELECT → se ejecuta con candado (solo SELECT,
un statement, LIMIT) → Claude redacta una respuesta breve con los datos reales. Nada inventado.

Modelo barato por defecto (Haiku). API key SOLO del entorno (ANTHROPIC_API_KEY) o config_local.API_KEY.
"""
import os
import re
import json
import db

MODEL = os.environ.get("LOVEO_MODEL", "claude-haiku-4-5")

SCHEMA = """Base SQLite del pipeline de licitaciones (Loveo Construcciones, Chile). Solo SELECT.
licitaciones(codigo, nombre, organismo, region, monto_estimado, moneda, fecha_cierre, fecha_visita,
  estado_mp, estado_revision, estado_resultado, score_provisional, fecha_descubierta, vigente_oferta, admisible)
  -- estado_revision: nueva|en_revision|aprobada|descartada
  -- estado_resultado: pendiente|presentada|ganada|perdida|desierta
  -- estado_mp (int): 5=publicada, 6=cerrada, 7=desierta, 8=adjudicada
  -- montos en CLP; fechas ISO 'YYYY-MM-DDTHH:MM:SS'
adjudicaciones(codigo, n_oferentes, fecha, monto_total)
items(codigo, nombre_producto, nombre_proveedor, rut_proveedor, monto_unitario, monto_total)
competidores(rut, razon_social, contacto)
participaciones(rut, codigo, gano)
eventos(codigo, ts, tipo, detalle)   -- tipo: descubierta|admisibilidad|score|cambio_estado|feedback|documento|nota
cubicaciones(proyecto, ingreso_sin_iva, costo_total, margen, margen_pct)
cubicacion_items(cubicacion_id, partida, grupo, descripcion, cantidad, unidad, precio_unitario, total)
precios_referencia(descripcion, unidad, precio_unitario, fuente, proyecto)"""

FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|vacuum|pragma|reindex)\b", re.I)


def _client():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        try:
            from config_local import API_KEY as key  # type: ignore
        except Exception:
            key = None
    if not key:
        raise RuntimeError("Falta ANTHROPIC_API_KEY en el entorno.")
    import anthropic
    return anthropic.Anthropic(api_key=key)


def _text(msg):
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()


def _gen_sql(client, question):
    msg = client.messages.create(
        model=MODEL, max_tokens=400,
        system=("Generás UNA consulta SQLite SELECT para responder la pregunta. Devolvés SOLO el SQL, "
                "un único statement, sin punto y coma final, sin markdown ni explicación.\n\n" + SCHEMA),
        messages=[{"role": "user", "content": question}],
    )
    txt = _text(msg)
    txt = re.sub(r"^```\w*|```$", "", txt, flags=re.M).strip()
    return txt


def _safe(sql):
    s = (sql or "").strip().rstrip(";").strip()
    if not re.match(r"(?is)^\s*select\b", s):
        return None
    if ";" in s or FORBIDDEN.search(s):
        return None
    return s


def _narrate(client, question, cols, rows):
    preview = [dict(zip(cols, r)) for r in rows[:30]]
    msg = client.messages.create(
        model=MODEL, max_tokens=350,
        system=("Respondé en español, breve y directo, usando SOLO estos datos (resultado de la consulta del "
                "usuario). Si está vacío, decí que no hay datos. No inventes ni agregues nada fuera de los datos."),
        messages=[{"role": "user", "content": f"Pregunta: {question}\nFilas ({len(rows)}): "
                                               f"{json.dumps(preview, ensure_ascii=False, default=str)}"}],
    )
    return _text(msg)


def ask(question):
    """Devuelve {ok, answer, sql, cols, rows}. Dos llamadas baratas (SQL + redacción)."""
    client = _client()
    sql_raw = _gen_sql(client, question)
    sql = _safe(sql_raw)
    if not sql:
        return {"ok": False, "answer": "No pude generar una consulta segura para esa pregunta.",
                "sql": sql_raw, "cols": [], "rows": []}
    try:
        with db.conn() as c:
            cur = c.execute(f"SELECT * FROM ({sql}) LIMIT 200")
            cols = [d[0] for d in cur.description]
            rows = [list(r) for r in cur.fetchall()]
    except Exception as e:
        return {"ok": False, "answer": f"La consulta no se pudo ejecutar: {e}", "sql": sql, "cols": [], "rows": []}
    answer = _narrate(client, question, cols, rows)
    return {"ok": True, "answer": answer, "sql": sql, "cols": cols, "rows": rows[:50]}


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "¿Cuántas licitaciones nuevas hay y cuál tiene el score más alto?"
    print(json.dumps(ask(q), ensure_ascii=False, indent=2, default=str))
