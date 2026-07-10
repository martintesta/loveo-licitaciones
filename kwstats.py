"""
kwstats.py — Atribución keyword→licitación + rendimiento por keyword (paso 2 de keywords).

  backfill()  — atribuye (incremental) qué keywords 'incluir' matchean el nombre de cada licitación
                que todavía no tiene atribución → tabla licitacion_keywords.
  stats()     — por término: cuántas matcheó, cuántas avanzaron, cuántas se descartaron, ganadas.

Mismo criterio de match que discover (límite de palabra, sin acentos, plural tolerante).
Sirve para que la inteligencia (paso 3/4) juzgue el valor de cada keyword.
"""
import db
import keywords as kwmod
from textnorm import na as _na, pat as _pat  # normalización compartida (una sola fuente de verdad)


def backfill():
    """Atribuye las licitaciones sin atribución todavía. Idempotente y barato."""
    inc, _, _ = kwmod.get_active_lists()
    pats = [(t, _pat(t)) for t in inc]
    with db.conn() as c:
        ya = {r[0] for r in c.execute("SELECT DISTINCT codigo FROM licitacion_keywords").fetchall()}
        rows = c.execute("SELECT codigo, nombre FROM licitaciones").fetchall()
        nuevos = 0
        for r in rows:
            if r["codigo"] in ya:
                continue
            n = _na(r["nombre"])
            for t, p in pats:
                if p.search(n):
                    c.execute("INSERT OR IGNORE INTO licitacion_keywords(codigo, termino, tipo) VALUES (?,?, 'incluir')",
                              (r["codigo"], t))
            nuevos += 1
    return nuevos


def stats():
    """Rendimiento por keyword (sobre todas las licitaciones atribuidas)."""
    with db.conn() as c:
        rows = c.execute("""
            SELECT lk.termino,
                   COUNT(*) AS matched,
                   SUM(CASE WHEN l.estado_revision IN ('en_revision','aprobada')
                             OR l.estado_resultado IN ('presentada','ganada') THEN 1 ELSE 0 END) AS avanzadas,
                   SUM(CASE WHEN l.estado_revision='descartada' THEN 1 ELSE 0 END) AS descartadas,
                   SUM(CASE WHEN l.estado_resultado='ganada' THEN 1 ELSE 0 END) AS ganadas
            FROM licitacion_keywords lk
            JOIN licitaciones l ON l.codigo = lk.codigo
            GROUP BY lk.termino
        """).fetchall()
    return {r["termino"]: {"matched": r["matched"], "avanzadas": r["avanzadas"] or 0,
                           "descartadas": r["descartadas"] or 0, "ganadas": r["ganadas"] or 0} for r in rows}
