"""
precios.py — Mantiene vivo el catálogo de precios (`precios_referencia`).

El costo es la mitad del GO/NO-GO: un precio de hace ocho meses hace que el margen mienta. Este
módulo es el que mantiene el catálogo al día, con tres reglas que no se negocian:

  1. NUNCA se pisa un precio. Cada cotización es un PUNTO NUEVO con su fecha (día y HORA), así
     conviven varios precios del mismo material y se puede ver la tendencia. `tendencia()` y el
     preciado siempre leen el más reciente.
  2. TODO precio guarda de dónde salió: `fuente` (valentina / web / manual / interno) y `source_url`
     con el link cuando vino de internet. Un precio sin trazabilidad no se puede auditar.
  3. La corrección MANUAL manda. Si Martín corrige un precio, ese es el último punto y el que se usa
     hasta que él lo cambie — el refresco mensual no lo pisa dentro de la ventana de gracia.

  refrescar(...)          -> re-cotiza por internet lo que está vencido (correr 1 vez al mes)
  corregir(desc, precio)  -> corrección manual (con link y nota opcionales)
  registrar(...)          -> agrega un punto (la primitiva que usan las dos de arriba)
  historial(desc)         -> todos los puntos de ese material, del más nuevo al más viejo
  vencidos(dias)          -> qué materiales toca re-cotizar

  python precios.py refrescar                          # el job mensual (respeta el vencimiento)
  python precios.py refrescar --todos --limite 20      # forzar, acotado
  python precios.py corregir "Container 20 pies" 3200000 --url https://... --nota "cotización X"
  python precios.py historial "Container 20 pies"
  python precios.py vencidos
"""
import datetime
import os

import cubicacion
import db
import schema_v3

# Un precio de mercado se da por vencido y se re-cotiza pasado este plazo. Un precio 'valentina'
# (lo que Loveo REALMENTE pagó) o 'manual' (corrección de Martín) no es una estimación: es un hecho,
# y no lo vence el reloj — pero sí se re-cotiza si quedó MUY viejo (ver VENCIMIENTO_HECHO_DIAS).
VENCIMIENTO_DIAS = int(os.environ.get("LOVEO_PRECIO_VENCE_DIAS", "45"))
VENCIMIENTO_HECHO_DIAS = int(os.environ.get("LOVEO_PRECIO_HECHO_VENCE_DIAS", "180"))

FUENTES_HECHO = {"valentina", "manual"}     # no son estimaciones de mercado: son hechos
MODEL = os.environ.get("LOVEO_MODEL_PRECIOS", "claude-sonnet-5")

# El buscador web nuevo (dynamic filtering) solo corre en los modelos recientes; en los viejos hay
# que mandar la variante básica o la API rechaza la herramienta.
_WEB_TOOL_NUEVO = {"claude-opus-5", "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6",
                   "claude-sonnet-5", "claude-sonnet-4-6", "claude-fable-5"}


def _ahora():
    """Timestamp con día Y HORA: dos cotizaciones del mismo día tienen que poder convivir y ordenarse."""
    return datetime.datetime.now().isoformat(sep=" ", timespec="seconds")


def _parse_fecha(v):
    if not v:
        return None
    try:
        return datetime.datetime.fromisoformat(str(v)[:19])
    except ValueError:
        return None


def _dias(fecha):
    f = _parse_fecha(fecha)
    return None if f is None else (datetime.datetime.now() - f).days


# ------------------------------------------------------------------ primitivas
def registrar(descripcion, precio, fuente="manual", url=None, unidad=None, proyecto=None,
              region=None, nota=None):
    """Agrega UN PUNTO al historial. Nunca hace UPDATE: es append-only por diseño.
    Devuelve {ok, id, fecha} o {ok: False, error}."""
    schema_v3.migrate()
    desc = (descripcion or "").strip()
    if not desc:
        return {"ok": False, "error": "Falta la descripción del material."}
    # Import local: cubicacion_ia delega la búsqueda web acá, así que a nivel módulo sería circular.
    # `_precio_num` entiende el formato CLP que Martín va a tipear ("$3.200.000", "3.200.000").
    import cubicacion_ia
    p = cubicacion_ia._precio_num(precio)
    if p is None or p <= 0:
        return {"ok": False, "error": f"Precio inválido: {precio!r}"}

    ts = _ahora()
    etiqueta = " · ".join(x for x in [desc, (f"[{nota}]" if nota else None)] if x)
    with db.conn() as c:
        c.execute("INSERT INTO precios_referencia (descripcion, descripcion_norm, unidad, "
                  "precio_unitario, fuente, proyecto, region, fecha, source_url) "
                  "VALUES (?,?,?,?,?,?,?,?,?)",
                  (etiqueta if nota else desc, cubicacion._na(desc), unidad, p, fuente,
                   proyecto, region, ts, url))
        row = c.execute("SELECT id FROM precios_referencia WHERE descripcion_norm=? AND fecha=? "
                        "ORDER BY id DESC LIMIT 1", (cubicacion._na(desc), ts)).fetchone()
    return {"ok": True, "id": (row[0] if row else None), "fecha": ts, "precio": p, "fuente": fuente}


def corregir(descripcion, precio, url=None, nota=None, unidad=None):
    """Corrección MANUAL. Queda como el punto más reciente y con fuente='manual', así el refresco
    mensual la respeta (ver `vencidos`) y el preciado la usa de inmediato."""
    return registrar(descripcion, precio, fuente="manual", url=url, unidad=unidad, nota=nota)


def historial(descripcion, n=20):
    """Todos los puntos de ese material, del más nuevo al más viejo. `id DESC` desempata la fecha:
    dos cargas en el mismo segundo empatan, pero el autoincrement sí refleja el orden real."""
    schema_v3.migrate()
    with db.conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT id, descripcion, precio_unitario, unidad, fuente, source_url, fecha "
            "FROM precios_referencia WHERE descripcion_norm=? AND precio_unitario IS NOT NULL "
            "ORDER BY fecha DESC, id DESC LIMIT ?", (cubicacion._na(descripcion), n)).fetchall()]


def catalogo():
    """Último punto por material (lo que ve el análisis). Uno por descripcion_norm."""
    schema_v3.migrate()
    with db.conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT descripcion, descripcion_norm, unidad, precio_unitario, fuente, source_url, fecha "
            "FROM precios_referencia WHERE precio_unitario IS NOT NULL "
            "ORDER BY fecha ASC, id ASC").fetchall()]
    cat = {}
    for r in rows:                    # ASC + sobrescritura → queda el más reciente por clave
        if r["descripcion_norm"]:
            cat[r["descripcion_norm"]] = r
    return cat


def vencidos(dias=None, dias_hecho=None, todos=False):
    """Qué materiales toca re-cotizar. Un precio de mercado ('web'/'interno') vence a los
    VENCIMIENTO_DIAS; uno que es un HECHO ('valentina'/'manual') aguanta mucho más, porque no es una
    estimación — pero tampoco es eterno."""
    dias = VENCIMIENTO_DIAS if dias is None else dias
    dias_hecho = VENCIMIENTO_HECHO_DIAS if dias_hecho is None else dias_hecho
    out = []
    for r in catalogo().values():
        edad = _dias(r["fecha"])
        tope = dias_hecho if r["fuente"] in FUENTES_HECHO else dias
        if todos or edad is None or edad > tope:
            out.append({**r, "dias": edad, "tope": tope})
    out.sort(key=lambda x: -(x["dias"] or 10**6))
    return out


# ------------------------------------------------------------------ búsqueda web
def buscar_precio_web(descripcion, unidad=None, modelo=None):
    """Cotiza un material en ecommerces chilenos y devuelve {precio, url} (o None).

    Es la fuente ÚNICA de búsqueda de precios del proyecto: `cubicacion_ia._buscar_web_real` delega
    acá. Defensiva por diseño: cualquier fallo devuelve None y el catálogo interno sigue sirviendo.
    Se apaga con LOVEO_PRECIOS_WEB=0."""
    if os.environ.get("LOVEO_PRECIOS_WEB", "1") == "0":
        return None
    if not (os.environ.get("ANTHROPIC_API_KEY") or _key_local()):
        return None
    modelo = modelo or MODEL
    try:
        import json

        import anthropic
        cl = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY") or _key_local())
        herramienta = ("web_search_20260209" if modelo in _WEB_TOOL_NUEVO else "web_search_20250305")
        pregunta = (
            f"Buscá en ecommerces y proveedores chilenos el precio unitario actual de: "
            f"'{descripcion}'" + (f" (unidad {unidad})" if unidad else "") + ".\n"
            "Devolvé SOLO un JSON: {\"precio_clp\": número o null, \"url\": \"link exacto del producto\" o null}.\n"
            "El precio es en CLP, sin IVA si el sitio lo separa. La URL tiene que ser la página del "
            "producto que muestra ese precio, no la home ni un buscador. Si no encontrás un precio "
            "confiable, devolvé null en los dos campos — no inventes.")
        msg = cl.messages.create(
            model=modelo, max_tokens=1200,
            tools=[{"type": herramienta, "name": "web_search", "max_uses": 4}],
            messages=[{"role": "user", "content": pregunta}])
        txt = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        crudo = txt[txt.find("{"):txt.rfind("}") + 1]
        data = json.loads(crudo) if crudo else {}
        precio = data.get("precio_clp")
        precio = float(precio) if isinstance(precio, (int, float)) else None
        return {"precio": precio, "url": data.get("url")} if precio else None
    except Exception:
        return None


def _key_local():
    try:
        from config_local import API_KEY
        return API_KEY
    except Exception:
        return None


# ------------------------------------------------------------------ el job mensual
def refrescar(limite=None, todos=False, buscar=None, dias=None):
    """Re-cotiza por internet los precios vencidos y guarda CADA resultado como punto nuevo con su
    link. Pensado para correr 1 vez al mes (`scripts/install_precios_task.ps1`).

    NO pisa nada: si la web no encuentra precio, el punto viejo sigue siendo el vigente.
    `buscar` es inyectable (tests sin red). Devuelve un resumen con la variación de cada material."""
    schema_v3.migrate()
    buscar = buscar or buscar_precio_web
    pendientes = vencidos(dias=dias, todos=todos)
    if limite:
        pendientes = pendientes[:int(limite)]

    actualizados, sin_precio, cambios = 0, [], []
    for it in pendientes:
        try:
            r = buscar(it["descripcion"], it["unidad"]) or {}
        except Exception:
            r = {}
        nuevo = r.get("precio")
        if not nuevo:
            sin_precio.append(it["descripcion"])
            continue
        anterior = it["precio_unitario"]
        res = registrar(it["descripcion"], nuevo, fuente="web", url=r.get("url"),
                        unidad=it["unidad"])
        if not res.get("ok"):
            sin_precio.append(it["descripcion"])
            continue
        actualizados += 1
        var = round(100 * (nuevo - anterior) / anterior, 1) if anterior else None
        cambios.append({"descripcion": it["descripcion"], "anterior": anterior, "nuevo": nuevo,
                        "variacion_pct": var, "url": r.get("url"),
                        "direccion": ("sube" if (var or 0) > 2 else
                                      "baja" if (var or 0) < -2 else "estable")})

    # Sin `db.log_evento`: `eventos.codigo` es NOT NULL y referencia a licitaciones — el refresco es
    # global, no de una licitación. La trazabilidad de este job vive donde corresponde: en los
    # propios puntos de `precios_referencia` (cada uno con su fecha, su fuente y su link).
    cambios.sort(key=lambda x: -abs(x["variacion_pct"] or 0))
    return {"ok": True, "revisados": len(pendientes), "actualizados": actualizados,
            "sin_precio": sin_precio, "cambios": cambios}


def _p(txt):
    """La consola de Windows es cp1252: no dejar que un '·' mate el reporte del job."""
    import sys
    codec = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(str(txt).encode(codec, errors="replace").decode(codec))


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Catálogo de precios: refresco mensual y correcciones.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("refrescar", help="re-cotiza por internet lo vencido (job mensual)")
    r.add_argument("--todos", action="store_true", help="ignorar el vencimiento y re-cotizar todo")
    r.add_argument("--limite", type=int, default=None, help="cortar después de N materiales")

    co = sub.add_parser("corregir", help="corrección manual de un precio")
    co.add_argument("descripcion")
    co.add_argument("precio")
    co.add_argument("--url", default=None)
    co.add_argument("--nota", default=None)
    co.add_argument("--unidad", default=None)

    h = sub.add_parser("historial", help="todos los puntos de un material")
    h.add_argument("descripcion")

    sub.add_parser("vencidos", help="qué materiales toca re-cotizar")

    a = ap.parse_args()
    if a.cmd == "refrescar":
        res = refrescar(limite=a.limite, todos=a.todos)
        _p(f"revisados: {res['revisados']} - actualizados: {res['actualizados']} - "
           f"sin cotizacion: {len(res['sin_precio'])}")
        for ch in res["cambios"][:25]:
            _p(f"  {ch['direccion']:8} {ch['variacion_pct']:>7}%  {ch['descripcion'][:52]:54} "
               f"{ch['anterior']:>12,.0f} -> {ch['nuevo']:>12,.0f}  {ch['url'] or ''}")
        for d in res["sin_precio"][:15]:
            _p(f"  (sin cotizacion) {d[:70]}")
    elif a.cmd == "corregir":
        res = corregir(a.descripcion, a.precio, url=a.url, nota=a.nota, unidad=a.unidad)
        _p(res if not res.get("ok") else
           f"OK: {a.descripcion[:60]} = {res['precio']:,.0f} (fuente manual, {res['fecha']})")
    elif a.cmd == "historial":
        for x in historial(a.descripcion):
            _p(f"  {x['fecha']}  {x['precio_unitario']:>12,.0f}  {x['fuente']:10} {x['source_url'] or ''}")
    elif a.cmd == "vencidos":
        v = vencidos()
        _p(f"{len(v)} materiales para re-cotizar")
        for x in v[:40]:
            _p(f"  {str(x['dias']):>5} dias (tope {x['tope']})  {x['fuente']:10} {x['descripcion'][:64]}")
