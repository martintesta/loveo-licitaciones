"""
notificar.py — Avisos de deadline (cierre / visita a terreno) por email. Cierra M-2.

En licitaciones el deadline ES el negocio: un cierre o una visita obligatoria que se pasan = deal
perdido (de hecho 'no fuimos a la visita' es una categoría del aprendizaje). alertas.py ya calcula
qué está por vencer; este módulo lo EMPUJA a un canal en vez de esperar que alguien abra el tablero.

  candidatas(hoy, umbral)  -> licitaciones EN JUEGO con cierre/visita dentro del umbral
  nuevas(cands)            -> las que aún no se notificaron (dedup por codigo+tipo+fecha_evento)
  correr(hoy, umbral, enviar) -> arma el digest de las nuevas, lo manda y las registra

Diseño:
  - Digest de las NUEVAS (las que recién entran a la ventana), no un re-envío diario → sin spam.
  - Dedup por (codigo, tipo, fecha_evento): si el deadline cambia, se vuelve a avisar.
  - SMTP por entorno, NUNCA hardcodeado. Sin config, degrada a no-op con log (como drive.disponible).
  - `enviar` es inyectable: los tests corren sin mandar un solo mail.

Config (env / .env):
  SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASS, SMTP_FROM, LOVEO_ALERT_TO (coma-separado)

  python notificar.py            # una pasada (para cron / Task Scheduler diario)
  python notificar.py --dry      # muestra a quién avisaría, sin enviar ni registrar
"""
import os
import smtplib
from email.mime.text import MIMEText

import db
import config
import schema_v3
import alertas

CANAL = "email"


def _destinatarios():
    return [x.strip() for x in os.environ.get("LOVEO_ALERT_TO", "").split(",") if x.strip()]


def disponible():
    """True si hay SMTP y destinatarios configurados (si no, correr() degrada a no-op)."""
    return bool(os.environ.get("SMTP_HOST") and _destinatarios())


def candidatas(hoy=None, umbral=None):
    """Licitaciones EN JUEGO (no descartadas ni cerradas) con cierre o visita dentro del umbral.

    Devuelve un item por evento: {codigo, nombre, organismo, region, score, tipo, fecha, dias}."""
    umbral = config.DIAS_ALERTA_CIERRE if umbral is None else umbral
    out = []
    with db.conn() as c:
        rows = c.execute(
            "SELECT codigo, nombre, organismo, region, score_provisional AS score, "
            "       fecha_cierre, fecha_visita "
            "FROM licitaciones "
            "WHERE estado_revision != 'descartada' "
            "  AND (estado_resultado IS NULL OR estado_resultado = 'pendiente')").fetchall()
    for r in rows:
        for tipo, fecha in (("cierre", r["fecha_cierre"]), ("visita", r["fecha_visita"])):
            dias = alertas.dias_hasta(fecha, hoy)
            if dias is not None and 0 <= dias <= umbral:
                out.append({"codigo": r["codigo"], "nombre": r["nombre"] or "—",
                            "organismo": r["organismo"] or "—", "region": r["region"] or "—",
                            "score": r["score"], "tipo": tipo, "fecha": fecha, "dias": dias})
    out.sort(key=lambda x: x["dias"])
    return out


def nuevas(cands):
    """Filtra las que TODAVÍA no se notificaron (dedup por codigo+tipo+fecha_evento)."""
    if not cands:
        return []
    codigos = tuple({x["codigo"] for x in cands})     # acota el scan a los candidatos, no toda la tabla
    ph = ",".join("?" for _ in codigos)
    with db.conn() as c:
        ya = {(r["codigo"], r["tipo"], r["fecha_evento"]) for r in c.execute(
            f"SELECT codigo, tipo, fecha_evento FROM notificaciones WHERE codigo IN ({ph})",
            codigos).fetchall()}
    return [x for x in cands if (x["codigo"], x["tipo"], x["fecha"]) not in ya]


def _dias_txt(d):
    return "HOY" if d == 0 else "mañana" if d == 1 else f"en {d} días"


def render(items):
    """(asunto, cuerpo) del digest. items = lista de candidatas nuevas."""
    n = len(items)
    asunto = f"Loveo · {n} deadline{'s' if n != 1 else ''} de licitación por vencer"
    lineas = ["Licitaciones que entran en la ventana de alerta:\n"]
    for it in items:
        que = "Cierre" if it["tipo"] == "cierre" else "Visita a terreno"
        sc = f" · score {it['score']}" if it["score"] is not None else ""
        lineas.append(f"• [{_dias_txt(it['dias']).upper()}] {que} — {it['nombre']} ({it['codigo']})")
        lineas.append(f"    {it['organismo']} · {it['region']}{sc} · {it['fecha']}")
    lineas.append("\n— Loveo Construcciones (aviso automático). No responder a este correo.")
    return asunto, "\n".join(lineas)


def _enviar_smtp(asunto, cuerpo, destinatarios):
    """Envía por SMTP con STARTTLS. Credenciales SOLO desde el entorno."""
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    remitente = os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER", "loveo@localhost")
    msg = MIMEText(cuerpo, "plain", "utf-8")
    msg["Subject"] = asunto
    msg["From"] = remitente
    msg["To"] = ", ".join(destinatarios)
    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls()
        user, pw = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASS")
        if user and pw:
            s.login(user, pw)
        s.sendmail(remitente, destinatarios, msg.as_string())


def correr(hoy=None, umbral=None, enviar=None):
    """Arma el digest de las nuevas, lo manda y las registra. `enviar` inyectable para tests.

    Devuelve {candidatas, nuevas, enviado, error?}. No envía nada si no hay nuevas o si falta SMTP."""
    schema_v3.migrate()
    cands = candidatas(hoy, umbral)
    frescas = nuevas(cands)
    if not frescas:
        return {"candidatas": len(cands), "nuevas": 0, "enviado": False}

    real = enviar is None
    if real and not disponible():
        return {"candidatas": len(cands), "nuevas": len(frescas), "enviado": False,
                "error": "SMTP/LOVEO_ALERT_TO no configurado (ver notificar.py). No se envió."}

    asunto, cuerpo = render(frescas)
    enviar = enviar or (lambda a, c, d: _enviar_smtp(a, c, d))
    try:
        enviar(asunto, cuerpo, _destinatarios())
    except Exception as e:   # si el envío falla NO registramos → se reintenta (mejor que perder el aviso)
        return {"candidatas": len(cands), "nuevas": len(frescas), "enviado": False,
                "error": f"falló el envío: {e}. No se registró; se reintenta la próxima pasada."}

    now = db._now()
    with db.conn() as c:
        for it in frescas:
            c.execute("INSERT OR IGNORE INTO notificaciones "
                      "(codigo, tipo, fecha_evento, canal, enviado_at) VALUES (?,?,?,?,?)",
                      (it["codigo"], it["tipo"], it["fecha"], CANAL, now))
    return {"candidatas": len(cands), "nuevas": len(frescas), "enviado": True}


if __name__ == "__main__":
    import sys
    if "--dry" in sys.argv:
        cands = candidatas()
        frescas = {(x["codigo"], x["tipo"], x["fecha"]) for x in nuevas(cands)}
        for it in cands:
            marca = "NUEVA" if (it["codigo"], it["tipo"], it["fecha"]) in frescas else "ya avisada"
            print(f"[{marca}] {it['tipo']} {_dias_txt(it['dias'])}: {it['codigo']} — {it['nombre']}")
    else:
        print(correr())
