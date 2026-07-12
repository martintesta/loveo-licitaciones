"""
cubicacion_ia.py — Cubicación asistida: BOM borrador desde las bases (Fase 1, spec cubicacion-asistida).

La Capa C ya lee las bases; su extracción trae `materiales` (lista {partida, grupo, descripcion,
cantidad, unidad}). Acá se persiste ese BORRADOR como una cubicaciones(origen='ia') + sus
cubicacion_items, para que el usuario lo cure. Es un borrador, NO una cotización.

Respeta la cubicación de Valentina: si existe una origen='valentina' para el código, esa MANDA y no
se genera la IA. Idempotente por (codigo, origen='ia'): regenerar reemplaza el borrador anterior.

  generar(codigo, extraer=None) -> {ok, items, error?}; `extraer` inyectable (real llama a Claude)
  borrador(codigo)              -> items del BOM IA guardado (para la UI); [] si no hay
"""
import db
import schema_v3

GRUPOS = {"material", "mano_obra", "transporte", "otros"}


def _extraer_real(codigo):
    import capa_c
    return capa_c.analizar_bases(codigo=codigo)


def _norm_item(m):
    """Normaliza un material de la extracción a las columnas de cubicacion_items (o None si no sirve)."""
    if not isinstance(m, dict):
        return None
    desc = str(m.get("descripcion") or m.get("partida") or "").strip()
    if not desc:
        return None
    grupo = str(m.get("grupo") or "material").strip().lower()
    if grupo not in GRUPOS:
        grupo = "material"
    cant = m.get("cantidad")
    try:
        cant = float(cant) if cant is not None and str(cant).strip() != "" else None
    except (ValueError, TypeError):
        cant = None
    return {"partida": (str(m.get("partida") or "").strip() or None), "grupo": grupo,
            "descripcion": desc, "cantidad": cant, "unidad": (str(m.get("unidad") or "").strip() or None)}


def generar(codigo, extraer=None):
    """Arma el BOM borrador (origen='ia') desde la extracción de las bases. Idempotente.
    Devuelve {ok, items} o {ok: False, error}. `extraer` inyectable (real llama a Claude)."""
    schema_v3.migrate()
    with db.conn() as c:
        val = c.execute("SELECT 1 FROM cubicaciones WHERE codigo=? AND origen='valentina'",
                        (codigo,)).fetchone()
    if val:
        return {"ok": False, "error": "Ya hay cubicación de Valentina (tiene prioridad); no se pisa."}

    extraer = extraer or _extraer_real
    res = extraer(codigo) or {}
    if res.get("error"):
        return {"ok": False, "error": res["error"]}
    ex = res.get("extraccion") or {}
    if ex.get("_parse_error"):   # igual que capac_score: respuesta de la IA ilegible
        return {"ok": False, "error": "No se pudo interpretar la respuesta de la IA. Reintentá."}
    mats = ex.get("materiales")
    items = [x for x in (_norm_item(m) for m in (mats if isinstance(mats, list) else [])) if x]
    if not items:
        return {"ok": False, "error": "La IA no extrajo materiales de las bases."}

    now = db._now()
    with db.conn() as c:
        cur = c.execute("SELECT id FROM cubicaciones WHERE codigo=? AND origen='ia'", (codigo,)).fetchone()
        if cur:   # idempotente: reemplazar el borrador anterior
            c.execute("DELETE FROM cubicacion_items WHERE cubicacion_id=?", (cur[0],))
            c.execute("DELETE FROM cubicaciones WHERE id=?", (cur[0],))
        c.execute("INSERT INTO cubicaciones (proyecto, codigo, origen, fecha) VALUES (?,?,?,?)",
                  (codigo, codigo, "ia", now))
        cub_id = c.execute("SELECT id FROM cubicaciones WHERE codigo=? AND origen='ia'",
                           (codigo,)).fetchone()[0]
        for it in items:
            c.execute("INSERT INTO cubicacion_items "
                      "(cubicacion_id, partida, grupo, descripcion, cantidad, unidad) VALUES (?,?,?,?,?,?)",
                      (cub_id, it["partida"], it["grupo"], it["descripcion"], it["cantidad"], it["unidad"]))
        db.log_evento(c, codigo, "cubicacion_ia", f"Borrador de cubicación IA: {len(items)} partidas.")
    return {"ok": True, "items": items}


def borrador(codigo):
    """Items del BOM IA guardado para la UI (o [] si no hay)."""
    schema_v3.migrate()
    with db.conn() as c:
        cur = c.execute("SELECT id FROM cubicaciones WHERE codigo=? AND origen='ia'", (codigo,)).fetchone()
        if not cur:
            return []
        return [dict(r) for r in c.execute(
            "SELECT partida, grupo, descripcion, cantidad, unidad, precio_unitario, total "
            "FROM cubicacion_items WHERE cubicacion_id=? ORDER BY id", (cur[0],)).fetchall()]
