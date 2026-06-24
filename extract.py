"""
extract.py — Extrae el bloque Adjudicacion + Items del json_detalle (ya guardado por discover.py)
hacia tablas estructuradas. Alimenta inteligencia competitiva y seguimiento de competencia.

  extraer(codigo, detalle:dict)   — procesa un detalle (dict de la API)
  extraer_todo()                  — recorre las licitaciones con json_detalle en la base

Qué puebla:
  adjudicaciones (cabecera) · items (con ganador por línea) · competidores · participaciones (ganadas)
Nota honesta: el ganador y el monto vienen de Items[].Adjudicacion. Las PERDIDAS necesitan las
ofertas públicas tras apertura técnica (otro endpoint) — quedan para una segunda fase.
"""
import json
import db


def _anio(fecha):
    return int(fecha[:4]) if fecha and len(fecha) >= 4 and fecha[:4].isdigit() else None


def extraer(codigo, detalle: dict, c=None):
    own = c is None
    if own:
        c = db.conn()
    try:
        adj = detalle.get("Adjudicacion") or {}
        fecha = adj.get("Fecha")
        if adj:
            c.execute("""INSERT INTO adjudicaciones(codigo,fecha,numero,n_oferentes,url_acta)
                         VALUES (?,?,?,?,?)
                         ON CONFLICT(codigo) DO UPDATE SET fecha=excluded.fecha,
                           numero=excluded.numero, n_oferentes=excluded.n_oferentes, url_acta=excluded.url_acta""",
                      (codigo, fecha, adj.get("Numero"), adj.get("NumeroOferentes"), adj.get("UrlActa")))

        items = (detalle.get("Items") or {}).get("Listado") or []
        c.execute("DELETE FROM items WHERE codigo=?", (codigo,))
        for it in items:
            ad = it.get("Adjudicacion") or {}
            cant = it.get("Cantidad")
            unit = ad.get("MontoUnitario")
            total = (cant or 0) * (unit or 0) if unit else None
            c.execute("""INSERT INTO items(codigo,nombre_producto,cantidad,unidad,
                          rut_proveedor,nombre_proveedor,monto_unitario,monto_total)
                          VALUES (?,?,?,?,?,?,?,?)""",
                      (codigo, it.get("NombreProducto"), cant, it.get("UnidadMedida"),
                       ad.get("RutProveedor"), ad.get("NombreProveedor"), unit, total))

            # competidor + participación ganada (si hay adjudicatario)
            rut = ad.get("RutProveedor")
            if rut:
                anio = _anio(fecha)
                c.execute("""INSERT INTO competidores(rut,razon_social,desde_anio)
                             VALUES (?,?,?)
                             ON CONFLICT(rut) DO UPDATE SET
                               razon_social=COALESCE(competidores.razon_social, excluded.razon_social),
                               desde_anio=MIN(COALESCE(competidores.desde_anio, 9999), COALESCE(excluded.desde_anio, 9999))""",
                          (rut, ad.get("NombreProveedor"), anio))
                c.execute("""INSERT INTO participaciones(rut,codigo,resultado,monto,anio)
                             VALUES (?,?,?,?,?)
                             ON CONFLICT(rut,codigo) DO UPDATE SET resultado='ganada',
                               monto=excluded.monto, anio=excluded.anio""",
                          (rut, codigo, "ganada", total, anio))
        if own:
            c.commit()
    finally:
        if own:
            c.close()


def extraer_todo():
    with db.conn() as c:
        filas = c.execute("SELECT codigo, json_detalle FROM licitaciones WHERE json_detalle IS NOT NULL").fetchall()
        n = 0
        for f in filas:
            try:
                extraer(f["codigo"], json.loads(f["json_detalle"]), c=c)
                n += 1
            except Exception as e:
                db.log_evento(c, f["codigo"], "error", f"extract: {e}")
    return n


if __name__ == "__main__":
    print("Licitaciones procesadas:", extraer_todo())
