"""
competencia.py — Agregados para la pestaña Seguimiento de Competencia.
Lee competidores + participaciones (que pobló extract.py) y entrega:

  resumen()              — una fila por competidor: participaciones, ganadas, perdidas, facturado total
  ficha(rut)             — detalle de un competidor + sus participaciones
  facturado_por_anio(rut)— dict {anio: monto} desde que participa en Mercado Público

Notas honestas:
  · 'ganadas' y 'facturado' salen del adjudicatario por ítem (Items[].Adjudicacion) — dato real.
  · 'perdidas' requiere las ofertas públicas tras apertura técnica (otro endpoint) → hoy 0.
  · 'contacto' no viene de la API de adjudicación → queda NULL (lookup de proveedor / manual).
  · 'facturado' usa el monto adjudicado como proxy; el facturado exacto vendría de Órdenes de Compra por RUT.
"""
import db


def resumen(limite=None):
    """Una fila por competidor. `limite` acota EN SQL (el tablero solo muestra el top 6: traer todo
    y cortar en Python materializa la tabla entera por render)."""
    with db.conn() as c:
        return [dict(r) for r in c.execute("""
            SELECT k.rut, k.razon_social, k.contacto, k.desde_anio,
                   COUNT(p.id)                                   AS participaciones,
                   SUM(CASE WHEN p.resultado='ganada'  THEN 1 ELSE 0 END) AS ganadas,
                   SUM(CASE WHEN p.resultado='perdida' THEN 1 ELSE 0 END) AS perdidas,
                   COALESCE(SUM(CASE WHEN p.resultado='ganada' THEN p.monto END),0) AS facturado_total
            FROM competidores k
            LEFT JOIN participaciones p ON p.rut = k.rut
            GROUP BY k.rut
            ORDER BY facturado_total DESC
        """ + ("LIMIT ?" if limite else ""), ((limite,) if limite else ())).fetchall()]


def facturado_por_anio(rut):
    with db.conn() as c:
        return {r["anio"]: r["monto"] for r in c.execute("""
            SELECT anio, COALESCE(SUM(monto),0) AS monto
            FROM participaciones
            WHERE rut=? AND resultado='ganada' AND anio IS NOT NULL
            GROUP BY anio ORDER BY anio
        """, (rut,)).fetchall()}


def ficha(rut):
    with db.conn() as c:
        comp = c.execute("SELECT * FROM competidores WHERE rut=?", (rut,)).fetchone()
        if not comp:
            return None
        parts = [dict(r) for r in c.execute("""
            SELECT p.codigo, p.resultado, p.monto, p.anio, l.nombre
            FROM participaciones p LEFT JOIN licitaciones l ON l.codigo=p.codigo
            WHERE p.rut=? ORDER BY p.anio DESC, p.monto DESC
        """, (rut,)).fetchall()]
        return {"competidor": dict(comp),
                "facturado_por_anio": facturado_por_anio(rut),
                "participaciones": parts}


if __name__ == "__main__":
    print("== resumen() ==")
    for r in resumen():
        print(f"  {r['razon_social']:42} part={r['participaciones']} G={r['ganadas']} P={r['perdidas']} facturado=${r['facturado_total']:,.0f}")
    print("\n== facturado_por_anio('76.383.813-7') ==")
    print(" ", facturado_por_anio("76.383.813-7"))
