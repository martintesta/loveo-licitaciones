"""
observabilidad.py — Captura de errores para producción (endurecer operación, #5).

Que un error en prod NO se pierda: se registra el traceback en la tabla `errores` (consultable
desde la app) y, si hay SENTRY_DSN, se reenvía a Sentry. La observabilidad NUNCA debe tumbar lo que
observa: todo va envuelto y falla en silencio.

  init()                       -> inicializa Sentry si hay SENTRY_DSN (no-op sin DSN / sin paquete)
  capturar(contexto, exc, msg) -> registra el error (traceback → tabla + Sentry)
  recientes(n)                 -> últimos errores no resueltos (para el panel/CLI)
  resolver(id)                 -> marca un error como resuelto
"""
import os
import traceback as _tb

import db
import schema_v3

_SENTRY = False


def init():
    """Inicializa Sentry si hay SENTRY_DSN y el paquete está. Devuelve True si quedó activo."""
    global _SENTRY
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return False
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=dsn, traces_sample_rate=0.0,
                        environment=os.environ.get("LOVEO_ENV", "prod"))
        _SENTRY = True
    except Exception:
        _SENTRY = False
    return _SENTRY


def capturar(contexto, exc=None, mensaje=None):
    """Registra un error (traceback → tabla `errores`) y lo reenvía a Sentry si está configurado.
    NUNCA lanza. `contexto` = de dónde viene (app / worker / run_daily / ...)."""
    try:
        # Del objeto (no del estado del except): funciona aunque se llame fuera de un `except`.
        tb = "".join(_tb.format_exception(type(exc), exc, exc.__traceback__)) if exc is not None else ""
        msg = (mensaje or (str(exc) if exc is not None else "") or "error")[:2000]
        schema_v3.migrate()
        with db.conn() as c:
            c.execute("INSERT INTO errores (ts, contexto, mensaje, traceback) VALUES (?,?,?,?)",
                      (db._now(), contexto, msg, tb[:8000]))
    except Exception:
        pass   # la observabilidad no puede romper el flujo que observa
    try:
        if os.environ.get("SENTRY_DSN"):
            import sentry_sdk
            if exc is not None:
                sentry_sdk.capture_exception(exc)
            else:
                sentry_sdk.capture_message(mensaje or "error")
    except Exception:
        pass


def recientes(n=50, incluir_resueltos=False):
    """Últimos errores (no resueltos por defecto) para el panel/CLI."""
    schema_v3.migrate()
    q = "SELECT id, ts, contexto, mensaje, traceback, resuelto FROM errores"
    if not incluir_resueltos:
        q += " WHERE resuelto=0"
    q += " ORDER BY id DESC LIMIT ?"
    with db.conn() as c:
        return [dict(r) for r in c.execute(q, (n,)).fetchall()]


def resolver(error_id):
    """Marca un error como resuelto (sale del panel). Castea el id (viene string del frontend)."""
    try:
        error_id = int(error_id)
    except (ValueError, TypeError):
        return
    schema_v3.migrate()
    with db.conn() as c:
        c.execute("UPDATE errores SET resuelto=1 WHERE id=?", (error_id,))


if __name__ == "__main__":
    for e in recientes():
        print(f"[{e['ts']}] ({e['contexto']}) {e['mensaje']}")
