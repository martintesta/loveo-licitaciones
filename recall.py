"""
recall.py — Auditoría de recall: qué descarta el filtro de discovery, y por qué.

El discovery estricto (discover.matchea) persiste SOLO lo que matchea INCLUIR sin EXCLUIR. Todo
lo demás se caía en silencio: no había forma de auditar falsos negativos (buenas que el filtro no
trajo) ni sobre-exclusiones. Este módulo clasifica cada licitación del día en un bucket y registra
las ACCIONABLES en `recall_log` para revisarlas.

Buckets (misma lógica de matcheo que discover: límite de palabra, sin acentos, plural s/es):
  estricto    -> matchea INCLUIR y ninguna EXCLUIR   (ya entra al embudo; NO se registra acá)
  recall      -> matchea la red AMPLIA pero NO la estricta  (candidata a revisar / falso negativo)
  excluido    -> matchea INCLUIR pero también una EXCLUIR    (posible sobre-exclusión)
  irrelevante -> no matchea nada                      (solo se cuenta)

  registrar_descartes(c, listado, fecha_run) -> {bucket: conteo}; graba recall+excluido (idempotente)
  auditar(limit)                             -> resumen de la cola pendiente para la UI
  resolver(codigo, accion)                   -> marca una fila como 'promovida' | 'descartada'
"""
import re
import unicodedata

import db
import schema_v3

ACCIONABLES = ("recall", "excluido")


def _na(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def _pat(term):
    # Igual que discover._pat: límite de palabra + plural s/es opcional.
    return re.compile(r"\b" + re.escape(_na(term)) + r"(?:e?s)?\b")


def _listas():
    """(inc_re, exc_re, amp_re, inc, exc, amp) desde la tabla keywords (fuente de verdad).

    exc incluye las EXCLUSIONES APRENDIDAS (exclusiones_aprendidas.txt) además de las de la tabla:
    así 'estricto' acá == matchea() del discovery (sin esa paridad, una lic vetada por una
    exclusión aprendida quedaría 'estricto' y jamás se auditaría → falso negativo silencioso)."""
    import keywords as kwmod
    inc, exc, amp = kwmod.get_active_lists()
    exc = list(exc) + _terminos_aprendidos()   # paridad con discover.matchea (exclusiones aprendidas)
    return ([_pat(k) for k in inc], [_pat(e) for e in exc], [_pat(a) for a in amp], inc, exc, amp)


def _terminos_aprendidos():
    """Términos crudos del archivo de exclusiones aprendidas (para clasificar como 'excluido')."""
    try:
        import discover
        if discover._LEARNED_FILE.exists():
            return [t.strip() for t in discover._LEARNED_FILE.read_text(encoding="utf-8").splitlines()
                    if t.strip() and not t.startswith("#")]
    except Exception:
        pass
    return []


def clasificar(nombre, listas=None):
    """(bucket, kw_match). kw_match: término(s) que explican el bucket (para mostrar el porqué)."""
    inc_re, exc_re, amp_re, inc, exc, amp = listas or _listas()
    n = _na(nombre)
    inc_hit = [k for k, rx in zip(inc, inc_re) if rx.search(n)]
    exc_hit = [k for k, rx in zip(exc, exc_re) if rx.search(n)]
    amp_hit = [k for k, rx in zip(amp, amp_re) if rx.search(n)]
    if inc_hit and not exc_hit:
        return "estricto", inc_hit
    if inc_hit and exc_hit:
        return "excluido", exc_hit       # matcheó incluir pero una exclusión lo bajó
    if amp_hit:
        return "recall", amp_hit         # solo la red amplia -> revisar
    return "irrelevante", []


def registrar_descartes(c, listado, fecha_run):
    """Clasifica el listado del día y graba las accionables (recall + excluido) en recall_log.

    Idempotente por (codigo, fecha_run) vía índice único. Devuelve el conteo por bucket para la
    trazabilidad del run. Recibe un cursor/conn abierto para sumarse a la misma transacción del
    discovery (una sola conexión)."""
    listas = _listas()
    counts = {"estricto": 0, "recall": 0, "excluido": 0, "irrelevante": 0}
    ts = db._now()
    for item in listado:
        nombre = item.get("Nombre", "")
        bucket, kw = clasificar(nombre, listas)
        counts[bucket] += 1
        if bucket in ACCIONABLES:
            c.execute(
                "INSERT OR IGNORE INTO recall_log (codigo, nombre, fecha_run, bucket, kw, ts) "
                "VALUES (?,?,?,?,?,?)",
                (item.get("CodigoExterno"), nombre, fecha_run, bucket, ", ".join(kw), ts))
    return counts


def auditar(limit=50):
    """Resumen de la cola de recall PENDIENTE para el panel de la UI.

    Abre su propia conexión: NO la llames dentro de un `with db.conn()` abierto (en SQLite los
    INSERTs de esa transacción todavía no serían visibles). La UI la usa standalone (build_data)."""
    schema_v3.migrate()
    with db.conn() as c:
        por_bucket = {r["bucket"]: r["n"] for r in c.execute(
            "SELECT bucket, COUNT(*) AS n FROM recall_log WHERE estado='pendiente' "
            "GROUP BY bucket").fetchall()}
        items = [dict(r) for r in c.execute(
            "SELECT codigo, nombre, fecha_run, bucket, kw FROM recall_log "
            "WHERE estado='pendiente' ORDER BY fecha_run DESC, id DESC LIMIT ?", (limit,)).fetchall()]
    return {"pendientes": sum(por_bucket.values()),
            "recall": por_bucket.get("recall", 0), "excluido": por_bucket.get("excluido", 0),
            "items": items}


def resolver(codigo, accion):
    """Marca todas las filas de un código como resueltas. accion: 'promovida' | 'descartada'."""
    if accion not in ("promovida", "descartada"):
        raise ValueError(f"acción inválida: {accion}")
    with db.conn() as c:
        c.execute("UPDATE recall_log SET estado=? WHERE codigo=?", (accion, codigo))
    return accion
