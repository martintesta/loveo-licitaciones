"""
cubicacion_ia.py — Cubicación asistida: BOM borrador desde las bases (Fase 1, spec cubicacion-asistida).

La Capa C ya lee las bases; su extracción trae `materiales` (lista {partida, grupo, descripcion,
cantidad, unidad}). Acá se persiste ese BORRADOR como una cubicaciones(origen='ia') + sus
cubicacion_items, para que el usuario lo cure. Es un borrador, NO una cotización.

Respeta la cubicación de Valentina: si existe una origen='valentina' para el código, esa MANDA y no
se genera la IA. Idempotente por (codigo, origen='ia'): regenerar reemplaza el borrador anterior.

  generar(codigo, extraer=None)     -> {ok, items, error?}; `extraer` inyectable (real llama a Claude)
  guardar_borrador(codigo, items)   -> reemplaza el borrador con la lista curada por el usuario
  preciar(codigo, buscar=None)      -> precia el BOM: catálogo interno + búsqueda web (source_url)
  borrador(codigo)                  -> items del BOM IA guardado (para la UI); [] si no hay
"""
import os
import re

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
            "SELECT partida, grupo, descripcion, cantidad, unidad, precio_unitario, total, "
            "precio_fuente, precio_url FROM cubicacion_items WHERE cubicacion_id=? ORDER BY id",
            (cur[0],)).fetchall()]


# ---------------------------------------------------------------- Fase 3: precios con referencia
def _precio_num(v):
    """Precio a float tolerando formato CLP: '$1.234.567'→1234567, '12.500'→12500 (punto=miles),
    '1.234,50'→1234.5 (coma decimal). None si no se puede."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d.,]", "", str(v))
    if not s:
        return None
    if "," in s:                                             # coma decimal, punto = miles
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") == 1 and len(s.split(".")[1]) == 2:    # un punto con 2 decimales → decimal
        pass
    else:                                                    # puntos = separador de miles (CLP)
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _buscar_web_real(descripcion, unidad):
    """Punto pluggable de la búsqueda web de precios (recomendación: catálogo interno + web con URL
    clickeable). Usa la herramienta de web search de Claude y devuelve {precio, url} o None.
    Defensivo: cualquier fallo → None (el precio interno igual funciona). Apagable con
    LOVEO_PRECIOS_WEB=0. El mecanismo exacto (Claude web search / API de búsqueda / scraping) se
    puede cambiar acá sin tocar el resto."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import json
        import anthropic
        cl = anthropic.Anthropic()
        pregunta = (f"Buscá en ecommerces chilenos (Sodimac, Easy, MercadoLibre, etc.) el precio de: "
                    f"'{descripcion}'" + (f" (unidad {unidad})" if unidad else "") + ". "
                    "Devolvé SOLO un JSON {\"precio_clp\": número, \"url\": \"la URL del producto\"}. "
                    "Si no encontrás un precio claro, devolvé {\"precio_clp\": null, \"url\": null}.")
        msg = cl.messages.create(
            model=os.environ.get("LOVEO_MODEL", "claude-haiku-4-5"), max_tokens=400,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
            messages=[{"role": "user", "content": pregunta}])
        txt = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        raw = txt[txt.find("{"):txt.rfind("}") + 1]
        data = json.loads(raw) if raw else {}
        precio = _precio_num(data.get("precio_clp"))
        return {"precio": precio, "url": data.get("url")} if precio is not None else None
    except Exception:
        return None


def preciar(codigo, buscar=None, web=None):
    """Precia el BOM IA: catálogo interno (precios_referencia) primero, y para los huecos una
    búsqueda web que deja el precio con su URL clickeable. Actualiza cubicacion_items y cachea los
    precios web en el catálogo propio. `buscar` inyectable (tests sin red). Devuelve
    {ok, preciados, web, sin_precio, costo}."""
    import cubicacion  # su _na fue la que escribió descripcion_norm en precios_referencia
    schema_v3.migrate()
    if web is None:
        web = os.environ.get("LOVEO_PRECIOS_WEB", "1") != "0"
    buscar = buscar or _buscar_web_real
    with db.conn() as c:
        cur = c.execute("SELECT id FROM cubicaciones WHERE codigo=? AND origen='ia'", (codigo,)).fetchone()
        if not cur:
            return {"ok": False, "error": "No hay borrador de cubicación para preciar."}
        rows = [dict(r) for r in c.execute(
            "SELECT id, descripcion, unidad, cantidad FROM cubicacion_items WHERE cubicacion_id=?",
            (cur[0],)).fetchall()]

    preciados = web_n = 0
    costo = 0.0
    for it in rows:
        norm = cubicacion._na(it["descripcion"])
        precio, fuente, url = None, None, None
        with db.conn() as c:   # 1) catálogo interno
            m = c.execute("SELECT precio_unitario, source_url FROM precios_referencia "
                          "WHERE descripcion_norm=? AND precio_unitario IS NOT NULL "
                          "ORDER BY fecha DESC", (norm,)).fetchone()
        if m:
            precio, fuente, url = m["precio_unitario"], "interno", m["source_url"]
        elif web:             # 2) búsqueda web (fuera de toda conexión abierta: es lento)
            try:
                r = buscar(it["descripcion"], it["unidad"]) or {}
            except Exception:
                r = {}
            precio = _precio_num(r.get("precio"))
            if precio is not None:
                fuente, url = "web", r.get("url")
                with db.conn() as c:   # cachear en el catálogo propio para la próxima
                    c.execute("INSERT INTO precios_referencia (descripcion, descripcion_norm, unidad, "
                              "precio_unitario, fuente, source_url, fecha) VALUES (?,?,?,?,?,?,?)",
                              (it["descripcion"], norm, it["unidad"], precio, "web", url, db._now()))
        if precio is not None:
            total = round(precio * it["cantidad"], 2) if it["cantidad"] is not None else None
            costo += total or 0
            preciados += 1
            web_n += 1 if fuente == "web" else 0
            with db.conn() as c:
                c.execute("UPDATE cubicacion_items SET precio_unitario=?, total=?, precio_fuente=?, "
                          "precio_url=? WHERE id=?", (precio, total, fuente, url, it["id"]))
    with db.conn() as c:
        db.log_evento(c, codigo, "cubicacion_ia",
                      f"Cubicación preciada: {preciados}/{len(rows)} partidas (web {web_n}). Costo ≈ {costo:.0f}.")
    return {"ok": True, "preciados": preciados, "web": web_n,
            "sin_precio": len(rows) - preciados, "costo": costo}
