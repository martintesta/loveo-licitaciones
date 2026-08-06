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
import textnorm

GRUPOS = {"material", "mano_obra", "transporte", "otros"}

# Tipo de producto para las recetas (Fase 5): agrupa licitaciones parecidas para reusar el BOM.
TIPOS_PRODUCTO = [
    ("contenedor", ["container", "conteiner", "contenedor"]),
    ("modular", ["modulo", "modular", "prefabricad", "sala", "oficina"]),
    ("bano", ["bano"]),
    ("reas", ["reas", "respel", "suspel"]),
    ("box", ["box"]),
    ("panel_solar", ["panel solar", "paneles solares"]),
]


def tipo_producto(nombre):
    """Clasifica el nombre de la licitación en un tipo de producto (o None). Base de las recetas."""
    n = textnorm.na(nombre)
    for tipo, kws in TIPOS_PRODUCTO:
        if any(k in n for k in kws):
            return tipo
    return None


def _extraer_real(codigo):
    import capa_c
    return capa_c.analizar_bases(codigo=codigo)


def _cantidad(v):
    """Cantidad a float, tolerando el formato chileno. None si no se puede.
    '1,5'→1.5 · '1.000,5'→1000.5 (coma=decimal, punto=miles) · '120'→120 · '1.5'→1.5 (decimal)
    · '1.000'→1000 y '2.500'→2500 (punto + 3 dígitos = MILES chileno).

    A diferencia de un precio CLP, en una cantidad los decimales cortos son legítimos (1.5 m²,
    2.75 ton), así que solo se trata como miles el patrón de 3 dígitos exactos tras el punto.
    Antes '1.000' daba 1.0 → costo ~1000× bajo → margen inflado."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d.,]", "", str(v)).strip()      # "120 un" → "120"
    if not s:
        return None
    if "," in s:                                     # coma decimal → el punto es de miles
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):      # 1.000 · 2.500 · 1.234.567 → miles
        s = s.replace(".", "")
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


def _reemplazar_items(c, codigo, items, preservar_precios=False):
    """Dentro de una conn abierta: reusa (o crea) la cubicación IA de `codigo` y reemplaza sus
    items por `items` (ya normalizados). No usa lastrowid: re-SELECT por (codigo, origen='ia').

    `preservar_precios=True` (curación del usuario): el form de la UI solo manda descripción/
    cantidad/unidad/grupo, así que un guardado borraba el PRECIADO ya pagado (precio, fuente, URL)
    y la `partida`. Se re-adjuntan por descripción normalizada; el `total` se RECALCULA con la
    cantidad nueva (arrastrarlo daría un costo viejo → margen mentiroso)."""
    cur = c.execute("SELECT id FROM cubicaciones WHERE codigo=? AND origen='ia'", (codigo,)).fetchone()
    previos = {}
    if cur:
        cub_id = cur[0]
        if preservar_precios:
            for r in c.execute("SELECT partida, descripcion, precio_unitario, precio_fuente, precio_url "
                               "FROM cubicacion_items WHERE cubicacion_id=?", (cub_id,)).fetchall():
                previos[textnorm.na(r["descripcion"] or "")] = r
        c.execute("DELETE FROM cubicacion_items WHERE cubicacion_id=?", (cub_id,))
    else:
        c.execute("INSERT INTO cubicaciones (proyecto, codigo, origen, fecha) VALUES (?,?,?,?)",
                  (codigo, codigo, "ia", db._now()))
        cub_id = c.execute("SELECT id FROM cubicaciones WHERE codigo=? AND origen='ia'",
                           (codigo,)).fetchone()[0]
    for it in items:
        p = previos.get(textnorm.na(it["descripcion"] or "")) if previos else None
        partida = it["partida"] or (p["partida"] if p else None)   # el form no renderiza `partida`
        pu = p["precio_unitario"] if p else None
        total = (pu * it["cantidad"]) if (pu is not None and it["cantidad"] is not None) else None
        c.execute("INSERT INTO cubicacion_items (cubicacion_id, partida, grupo, descripcion, cantidad, "
                  "unidad, precio_unitario, total, precio_fuente, precio_url) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (cub_id, partida, it["grupo"], it["descripcion"], it["cantidad"], it["unidad"],
                   pu, total, (p["precio_fuente"] if p else None), (p["precio_url"] if p else None)))
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


def _reemplazar_receta(c, tipo, items):
    """Guarda (dentro de una conn abierta) la receta del tipo de producto: cubicaciones(origen=
    'receta', proyecto=tipo) + items. Reemplaza la receta anterior de ese tipo."""
    cur = c.execute("SELECT id FROM cubicaciones WHERE proyecto=? AND origen='receta'", (tipo,)).fetchone()
    if cur:
        cub_id = cur[0]
        c.execute("DELETE FROM cubicacion_items WHERE cubicacion_id=?", (cub_id,))
    else:
        c.execute("INSERT INTO cubicaciones (proyecto, origen, fecha) VALUES (?,?,?)",
                  (tipo, "receta", db._now()))
        cub_id = c.execute("SELECT id FROM cubicaciones WHERE proyecto=? AND origen='receta'",
                           (tipo,)).fetchone()[0]
    for it in items:
        c.execute("INSERT INTO cubicacion_items "
                  "(cubicacion_id, partida, grupo, descripcion, cantidad, unidad) VALUES (?,?,?,?,?,?)",
                  (cub_id, it["partida"], it["grupo"], it["descripcion"], it["cantidad"], it["unidad"]))


def _recomputar_receta(c, tipo):
    """Recomputa la receta del tipo AGREGANDO todas las cubicaciones IA curadas de licitaciones de
    ese tipo (consenso), en vez de 'última gana' (Fase 4). Por partida (clave = descripción
    normalizada) toma la cantidad MEDIANA y conserva solo las que aparecen en al menos la mitad de
    las cubicaciones del tipo — así la receta filtra el ruido de una sola curación y encarna lo que
    de verdad se repite. Con una sola cubicación equivale a copiarla (no hay regresión en cold-start)."""
    import statistics
    filas = c.execute(
        "SELECT cu.codigo AS codigo, l.nombre AS nombre, ci.descripcion AS descripcion, "
        "ci.grupo AS grupo, ci.unidad AS unidad, ci.partida AS partida, ci.cantidad AS cantidad "
        "FROM cubicacion_items ci "
        "JOIN cubicaciones cu ON cu.id = ci.cubicacion_id "
        "JOIN licitaciones l ON l.codigo = cu.codigo "
        "WHERE cu.origen='ia' AND cu.curada=1").fetchall()   # solo curaciones del usuario, no borradores IA crudos
    por_codigo = {}
    for r in filas:
        if tipo_producto(r["nombre"] or "") == tipo:
            por_codigo.setdefault(r["codigo"], []).append(r)
    n_cub = len(por_codigo)
    if not n_cub:
        return
    acc = {}                                   # clave -> datos + cantidades + códigos que la traen
    for cod, its in por_codigo.items():
        vistas = set()                         # una lic cuenta UNA vez por clave (no infla la mediana)
        for it in its:
            clave = textnorm.na(it["descripcion"])
            d = acc.setdefault(clave, {"descripcion": it["descripcion"], "grupo": it["grupo"],
                                       "unidad": it["unidad"], "partida": it["partida"],
                                       "cantidades": [], "codigos": set()})
            d["codigos"].add(cod)
            if it["cantidad"] is not None and clave not in vistas:
                d["cantidades"].append(it["cantidad"])
                vistas.add(clave)
    receta = []
    for d in acc.values():
        if len(d["codigos"]) * 2 >= n_cub:     # aparece en ≥ la mitad → consenso
            cant = round(statistics.median(d["cantidades"]), 2) if d["cantidades"] else None
            receta.append({"partida": d["partida"], "grupo": d["grupo"],
                           "descripcion": d["descripcion"], "cantidad": cant, "unidad": d["unidad"]})
    if receta:
        _reemplazar_receta(c, tipo, receta)


def guardar_borrador(codigo, items):
    """Reemplaza el borrador IA con la lista CURADA por el usuario (Fase 2). Normaliza y descarta
    las filas sin descripción. Crea la cubicación IA si no existía. Respeta la de Valentina.
    Además RECOMPUTA la receta del tipo (consenso de todas las curaciones): la inteligencia propia."""
    schema_v3.migrate()
    if _tiene_valentina(codigo):
        return {"ok": False, "error": "Hay cubicación de Valentina; no se edita el borrador IA."}
    norm = [x for x in (_norm_item(m) for m in (items or [])) if x]
    with db.conn() as c:
        correcciones = _diff_curacion(c, codigo, norm)   # ANTES de reemplazar: qué cambió el usuario
        cub_id = _reemplazar_items(c, codigo, norm, preservar_precios=True)  # no perder el preciado
        c.execute("UPDATE cubicaciones SET curada=1 WHERE id=?", (cub_id,))  # esta cubicación ya es curada
        nombre = c.execute("SELECT nombre FROM licitaciones WHERE codigo=?", (codigo,)).fetchone()
        tipo = tipo_producto(nombre["nombre"] if nombre else "")
        if tipo and norm:                      # cada curación recompone la receta (consenso del tipo)
            _recomputar_receta(c, tipo)
        db.log_evento(c, codigo, "cubicacion_ia",
                      f"Cubicación curada: {len(norm)} partidas." + (f" Receta '{tipo}' actualizada." if tipo and norm else ""))
    return {"ok": True, "items": norm, "receta_tipo": tipo, "correcciones": correcciones}


def _diff_curacion(c, codigo, nuevos):
    """Qué CORRIGIÓ el usuario respecto de lo que el sistema había propuesto: partidas agregadas,
    quitadas y cantidades cambiadas. Es la señal más informativa del motor (dice qué estaba MAL,
    no solo qué le importa) y hasta ahora se perdía entera. Devuelve {agregadas, quitadas, ajustadas}
    o None si no había borrador previo (primera curación: no hay contra qué comparar)."""
    cur = c.execute("SELECT id FROM cubicaciones WHERE codigo=? AND origen='ia'", (codigo,)).fetchone()
    if not cur:
        return None
    previos = {textnorm.na(r["descripcion"] or ""): r["cantidad"] for r in c.execute(
        "SELECT descripcion, cantidad FROM cubicacion_items WHERE cubicacion_id=?", (cur[0],)).fetchall()}
    if not previos:
        return None
    ahora = {textnorm.na(i["descripcion"] or ""): i["cantidad"] for i in nuevos}
    agregadas = [k for k in ahora if k not in previos]
    quitadas = [k for k in previos if k not in ahora]
    ajustadas = [k for k in ahora if k in previos and ahora[k] != previos[k]]
    if not (agregadas or quitadas or ajustadas):
        return None                     # guardó sin cambiar nada: no es una corrección
    return {"agregadas": len(agregadas), "quitadas": len(quitadas), "ajustadas": len(ajustadas)}


def prellenar_desde_receta(codigo):
    """Pre-llena el borrador de una licitación desde la receta de su tipo de producto (sin IA).
    Es la 'aceleración': una lic parecida arranca con el BOM de la receta para solo ajustar deltas.
    Respeta la cubicación de Valentina. Devuelve {ok, items, tipo} o {ok: False, error}."""
    schema_v3.migrate()
    if _tiene_valentina(codigo):
        return {"ok": False, "error": "Ya hay cubicación de Valentina (tiene prioridad); no se pisa."}
    with db.conn() as c:
        nombre = c.execute("SELECT nombre FROM licitaciones WHERE codigo=?", (codigo,)).fetchone()
        tipo = tipo_producto(nombre["nombre"] if nombre else "")
        if not tipo:
            return {"ok": False, "error": "No se pudo determinar el tipo de producto de la licitación."}
        rec = c.execute("SELECT id FROM cubicaciones WHERE proyecto=? AND origen='receta'", (tipo,)).fetchone()
        if not rec:
            return {"ok": False, "error": f"Todavía no hay receta para el tipo '{tipo}'. Curá una y se aprende."}
        items = [dict(r) for r in c.execute(
            "SELECT partida, grupo, descripcion, cantidad, unidad FROM cubicacion_items "
            "WHERE cubicacion_id=? ORDER BY id", (rec[0],)).fetchall()]
    if not items:
        return {"ok": False, "error": "La receta está vacía."}
    with db.conn() as c:
        _reemplazar_items(c, codigo, items)
        db.log_evento(c, codigo, "cubicacion_ia",
                      f"Borrador pre-llenado desde receta '{tipo}': {len(items)} partidas.")
    return {"ok": True, "items": items, "tipo": tipo}


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


# ---------------------------------------------------------------- Fase 4: margen real → score
try:
    from config import MARGEN_TIERS
except (ImportError, AttributeError):
    MARGEN_TIERS = [(30, 9), (20, 7), (10, 5), (0, 3)]   # (margen % mínimo, score 0-10); < 0 → 1


def _score_margen(pct):
    if pct is None:
        return 5
    for minimo, s in MARGEN_TIERS:
        if pct >= minimo:
            return s
    return 1


def margen(codigo):
    """Costo (BOM preciado) vs techo de presupuesto (Capa C) → margen real. Si TODAS las partidas
    están preciadas, actualiza la dimensión 'margen' del score (evaluada, display, reversible) y
    guarda costo/margen en la cubicación. Si faltan precios, devuelve el estimado SIN tocar el score.
    Devuelve {ok, aplicado, costo, techo, margen, margen_pct, sin_precio, score_antes?, score_despues?}."""
    import json
    import scoring
    schema_v3.migrate()
    with db.conn() as c:
        cur = c.execute("SELECT id FROM cubicaciones WHERE codigo=? AND origen='ia'", (codigo,)).fetchone()
        if not cur:
            return {"ok": False, "error": "No hay cubicación para calcular margen."}
        cub_id = cur[0]
        rows = [dict(r) for r in c.execute(
            "SELECT total, precio_unitario FROM cubicacion_items WHERE cubicacion_id=?", (cub_id,)).fetchall()]
        a = c.execute("SELECT presupuesto_clp FROM analisis_bases WHERE codigo=? AND presupuesto_clp IS NOT NULL "
                      "ORDER BY id DESC", (codigo,)).fetchone()
        lic = c.execute("SELECT score_provisional, score_json FROM licitaciones WHERE codigo=?",
                        (codigo,)).fetchone()
        techo = a["presupuesto_clp"] if a else None            # extraído dentro del with (row-safe en PG)
        score_antes = lic["score_provisional"] if lic else None
        score_json_str = lic["score_json"] if lic else None
    if not rows:
        return {"ok": False, "error": "La cubicación no tiene partidas."}
    # "sin costo" = sin total: le falta el PRECIO o la CANTIDAD (la IA devuelve cantidad=null cuando
    # no hay dato). El gate se cierra sobre el total, no sobre el precio: un ítem con precio pero sin
    # cantidad aporta $0 al costo y NO debe dejar aplicar el margen al score (subestimaría el costo).
    sin_precio = sum(1 for r in rows if r["total"] is None)
    costo = sum(r["total"] or 0 for r in rows)
    if not techo:
        return {"ok": False, "error": "Falta el techo de presupuesto (analizá las bases con Capa C)."}
    m = techo - costo
    m_pct = round(100 * m / techo, 1) if techo else None
    base = {"ok": True, "costo": costo, "techo": techo, "margen": m, "margen_pct": m_pct,
            "sin_precio": sin_precio}

    if sin_precio > 0:   # honestidad: el margen al score solo si TODO está preciado
        base["aplicado"] = False
        return base

    with db.conn() as c:
        c.execute("UPDATE cubicaciones SET costo_total=?, margen=?, margen_pct=? WHERE id=?",
                  (costo, m, m_pct, cub_id))
        sj = json.loads(score_json_str) if score_json_str else {"dimensiones": {}}
        dims = sj.get("dimensiones", {})
        sc = _score_margen(m_pct)
        dims["margen"] = {"score": sc, "evaluado": True,
                          "nota": f"Margen {m_pct}% (costo ${costo:,.0f} vs techo ${techo:,.0f}) "
                                  f"por cubicación asistida.".replace(",", ".")}
        sj["dimensiones"] = dims
        total = sum(dims[d]["score"] * scoring.PESOS[d] for d in scoring.PESOS if d in dims)
        sj["score_provisional"] = total
        sj["triage"] = scoring.triage(total)
        # confianza al día: margen ahora evaluado → suma sus puntos a los "evaluables" (era stale).
        sj["evaluable_pts"] = sum(scoring.PESOS[d] for d in scoring.PESOS
                                  if d in dims and dims[d].get("evaluado")) * 10
        requiere = any(not dims[d].get("evaluado") for d in dims)
        sj["requiere_bases"] = requiere
        db.set_score_provisional(c, codigo, total, json.dumps(sj, ensure_ascii=False), requiere)
        db.log_evento(c, codigo, "cubicacion_ia",
                      f"Margen aplicado al score: {m_pct}% → dimensión margen {sc}/10. "
                      f"Score {score_antes}→{total}.")
    base.update({"aplicado": True, "score_antes": score_antes, "score_despues": total})
    return base
