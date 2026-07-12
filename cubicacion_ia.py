"""
cubicacion_ia.py — Cubicación asistida: BOM borrador desde las bases (Fase 1, spec cubicacion-asistida).

La Capa C ya lee las bases; su extracción trae `materiales` (lista {partida, grupo, descripcion,
cantidad, unidad}). Acá se persiste ese BORRADOR como una cubicaciones(origen='ia') + sus
cubicacion_items, para que el usuario lo cure. Es un borrador, NO una cotización.

Respeta la cubicación de Valentina: si existe una origen='valentina' para el código, esa MANDA y no
se genera la IA. Idempotente por (codigo, origen='ia'): regenerar reemplaza el borrador anterior.

  generar(codigo, extraer=None)     -> {ok, items, error?}; `extraer` inyectable (real llama a Claude)
  guardar_borrador(codigo, items)   -> reemplaza el borrador con la lista curada por el usuario
  borrador(codigo)                  -> items del BOM IA guardado (para la UI); [] si no hay
"""
import db
import schema_v3

GRUPOS = {"material", "mano_obra", "transporte", "otros"}


def _extraer_real(codigo):
    import capa_c
    return capa_c.analizar_bases(codigo=codigo)


def _cantidad(v):
    """Cantidad a float, tolerando el formato chileno (coma decimal). None si no se puede.
    '1,5'→1.5 · '1.000,5'→1000.5 (coma=decimal, punto=miles) · '120'→120 · '1.5'→1.5 (sin coma)."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    if "," in s:                       # formato chileno: el punto es separador de miles
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


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
    cant = _cantidad(m.get("cantidad"))
    return {"partida": (str(m.get("partida") or "").strip() or None), "grupo": grupo,
            "descripcion": desc, "cantidad": cant, "unidad": (str(m.get("unidad") or "").strip() or None)}


def _tiene_valentina(codigo):
    with db.conn() as c:
        return c.execute("SELECT 1 FROM cubicaciones WHERE codigo=? AND origen='valentina'",
                         (codigo,)).fetchone() is not None


def _reemplazar_items(c, codigo, items):
    """Dentro de una conn abierta: reusa (o crea) la cubicación IA de `codigo` y reemplaza sus
    items por `items` (ya normalizados). No usa lastrowid: re-SELECT por (codigo, origen='ia')."""
    cur = c.execute("SELECT id FROM cubicaciones WHERE codigo=? AND origen='ia'", (codigo,)).fetchone()
    if cur:
        cub_id = cur[0]
        c.execute("DELETE FROM cubicacion_items WHERE cubicacion_id=?", (cub_id,))
    else:
        c.execute("INSERT INTO cubicaciones (proyecto, codigo, origen, fecha) VALUES (?,?,?,?)",
                  (codigo, codigo, "ia", db._now()))
        cub_id = c.execute("SELECT id FROM cubicaciones WHERE codigo=? AND origen='ia'",
                           (codigo,)).fetchone()[0]
    for it in items:
        c.execute("INSERT INTO cubicacion_items "
                  "(cubicacion_id, partida, grupo, descripcion, cantidad, unidad) VALUES (?,?,?,?,?,?)",
                  (cub_id, it["partida"], it["grupo"], it["descripcion"], it["cantidad"], it["unidad"]))
    return cub_id


def generar(codigo, extraer=None):
    """Arma el BOM borrador (origen='ia') desde la extracción de las bases. Idempotente.
    Devuelve {ok, items} o {ok: False, error}. `extraer` inyectable (real llama a Claude)."""
    schema_v3.migrate()
    if _tiene_valentina(codigo):
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

    with db.conn() as c:
        _reemplazar_items(c, codigo, items)
        db.log_evento(c, codigo, "cubicacion_ia", f"Borrador de cubicación IA: {len(items)} partidas.")
    return {"ok": True, "items": items}


def guardar_borrador(codigo, items):
    """Reemplaza el borrador IA con la lista CURADA por el usuario (Fase 2). Normaliza y descarta
    las filas sin descripción. Crea la cubicación IA si no existía. Respeta la de Valentina."""
    schema_v3.migrate()
    if _tiene_valentina(codigo):
        return {"ok": False, "error": "Hay cubicación de Valentina; no se edita el borrador IA."}
    norm = [x for x in (_norm_item(m) for m in (items or [])) if x]
    with db.conn() as c:
        _reemplazar_items(c, codigo, norm)
        db.log_evento(c, codigo, "cubicacion_ia", f"Cubicación curada: {len(norm)} partidas.")
    return {"ok": True, "items": norm}


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
