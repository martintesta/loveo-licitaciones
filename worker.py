"""
worker.py — Worker residencial (Capa B: descarga de bases + futura Ficha Comprador).

POR QUÉ EXISTE: el endpoint de adjuntos de Mercado Público y la Ficha Comprador bloquean
accesos automatizados de datacenter (403 / captcha). La UI hosteada (Render) NO hace esto;
solo este worker, que corre en una máquina con IP CHILENA RESIDENCIAL (tu notebook prendido).

QUÉ HACE (dos etapas por pasada, desacopladas):
  1. Capa B: polling de la MISMA base (DATABASE_URL → Neon), busca admisibles con
     docs_estado='pendiente' y baja sus bases reusando download.descargar_codigo.
  2. Capa C: para las bases YA bajadas sin análisis todavía, corre capac_score.analizar →
     recalibra COMPLEJIDAD (neutro→real) y suma el techo de presupuesto. Así el score deja de
     ser 4/6 y pasa a 5/6 dimensiones SIN intervención (margen sigue pendiente de la cubicación).

Desacoplar las dos etapas hace que un análisis que falla se reintente en la próxima pasada, y
que una base bajada a mano desde la UI también termine analizada. Ver WORKER.md para el deploy.

  python worker.py            # loop infinito (intervalo LOVEO_WORKER_INTERVAL seg; default 120)
  python worker.py --once     # una sola pasada y termina

Capa C se puede apagar con LOVEO_WORKER_CAPAC=0 (worker solo-descarga). La descarga real
(Playwright) y el análisis real (Claude) se importan PEREZOSAMENTE y son inyectables: el loop
se testea sin Playwright, sin IP chilena y sin gastar tokens.
"""
import os
import time
import datetime

import db  # db._load_dotenv() corre en su import y puebla .env (self-contained; ver db.py)
import schema_v3


def pendientes(limit=20):
    """Licitaciones admisibles con bases sin bajar (mismo criterio que download.pendientes)."""
    with db.conn() as c:
        return [r[0] for r in c.execute(
            "SELECT codigo FROM licitaciones WHERE admisible=1 AND docs_estado='pendiente' "
            "ORDER BY fecha_actualizada DESC LIMIT ?", (limit,)).fetchall()]


def procesar(codigo, descargar):
    """Procesa UNA licitación con la función de descarga inyectada (real o mock).

    La descarga real (download.descargar_codigo) maneja su propio docs_estado y devuelve un dict
    {ok, nota, ...}. Acá normalizamos a {ok, muro} para el conteo y el heartbeat, y cubrimos el
    caso de EXCEPCIÓN (marcar 'error' + traza). `muro` = chocó con el muro anti-bot.
    """
    try:
        r = descargar(codigo)
        if isinstance(r, dict):   # descarga real
            return {"ok": bool(r.get("ok")), "muro": "anti-bot" in (r.get("nota") or "").lower()}
        return {"ok": bool(r), "muro": False}   # compat con mocks que devuelven bool
    except Exception as e:
        with db.conn() as c:
            # no pisar un 'descargado' exitoso si la excepción llegó tarde
            c.execute("UPDATE licitaciones SET docs_estado='error' "
                      "WHERE codigo=? AND docs_estado!='descargado'", (codigo,))
            db.log_evento(c, codigo, "error", f"worker: descarga falló: {e}")
        return {"ok": False, "muro": False}


def pendientes_capac(limit=20):
    """Bases YA bajadas pero sin análisis de Capa C todavía (complejidad aún en neutro).

    Se apoya en analisis_bases (la crea schema_v3): una vez que existe una fila para el código,
    ya no reaparece. Un análisis fallido no deja fila → se reintenta la próxima pasada."""
    with db.conn() as c:
        return [r[0] for r in c.execute(
            "SELECT codigo FROM licitaciones WHERE admisible=1 AND docs_estado='descargado' "
            "AND codigo NOT IN (SELECT codigo FROM analisis_bases) "
            "ORDER BY fecha_actualizada DESC LIMIT ?", (limit,)).fetchall()]


def procesar_capac(codigo, analizar):
    """Corre Capa C sobre UNA licitación con bases bajadas. Devuelve True si el análisis aplicó.
    Un error nunca frena la pasada: se loguea y se reintenta la próxima vez (no deja fila)."""
    try:
        r = analizar(codigo) or {}
        if not r.get("ok"):
            with db.conn() as c:
                db.log_evento(c, codigo, "capa_c", f"worker: Capa C no aplicada: {r.get('error', 'desconocido')}")
            return False
        return True
    except Exception as e:
        with db.conn() as c:
            db.log_evento(c, codigo, "error", f"worker: Capa C falló: {e}")
        return False


def _descargar_real(codigo):
    # Import perezoso: download.py trae Playwright, que NO hace falta para testear el loop.
    import download
    return download.descargar_codigo(codigo)


def _analizar_real(codigo):
    # Import perezoso: capac_score llama a Claude. Inyectable para testear sin gastar tokens.
    import capac_score
    return capac_score.analizar(codigo)


def ficha_comprador(organismo):
    """TODO (worker residencial): leer la Ficha Comprador — comportamiento de pago del comprador,
    detrás del WAF + CAPTCHA de www.mercadopublico.cl (no automatizable de forma confiable ni
    desde IP residencial). El día que se pueda, esto debe llamar
    comprador.set_reputacion(organismo, nivel, nota, fuente='ficha_comprador') para escribir en la
    MISMA tabla que hoy se llena a mano desde la ficha. Mientras tanto, la reputación se carga
    manualmente (ver comprador.py y WORKER.md)."""
    raise NotImplementedError(
        "Ficha Comprador: bloqueada por CAPTCHA. Cargá la reputación a mano desde la ficha "
        "(alimenta comprador.set_reputacion). Ver WORKER.md.")


def registrar_salud(pendientes, bajadas, capac, muro):
    """Heartbeat: deja en worker_estado (fila única) qué pasó en esta pasada. `ultimo_ok` solo
    avanza si la pasada fue SANA — bajó algo o no había backlog. Si hay backlog y no bajó nada
    (muro / notebook con problemas), ultimo_ok NO avanza → salud() lo detecta como silencio."""
    now = db._now()
    sana = bajadas > 0 or pendientes == 0
    with db.conn() as c:
        existe = c.execute("SELECT 1 FROM worker_estado WHERE id=1").fetchone()
        if existe:
            c.execute("UPDATE worker_estado SET ultimo_intento=?, pendientes=?, bajadas=?, capac=?, "
                      "muro=?, ultimo_ok=CASE WHEN ? THEN ? ELSE ultimo_ok END WHERE id=1",
                      (now, pendientes, bajadas, capac, 1 if muro else 0, sana, now))
        else:
            c.execute("INSERT INTO worker_estado (id, ultimo_ok, ultimo_intento, pendientes, bajadas, "
                      "capac, muro) VALUES (1,?,?,?,?,?,?)",
                      (now if sana else None, now, pendientes, bajadas, capac, 1 if muro else 0))


def salud(umbral_horas=None, hoy=None):
    """Estado del worker para alertas/UI. stale = hay backlog Y hace > umbral horas que no procesa.
    umbral_horas None lee LOVEO_WORKER_STALE_H (default 24)."""
    umbral = int(os.environ.get("LOVEO_WORKER_STALE_H", "24")) if umbral_horas is None else umbral_horas
    schema_v3.migrate()
    with db.conn() as c:
        r = c.execute("SELECT ultimo_ok, ultimo_intento, pendientes, muro FROM worker_estado "
                      "WHERE id=1").fetchone()
    if not r:
        return {"conocido": False, "stale": False, "pendientes": 0, "muro": False,
                "horas": None, "ultimo_ok": None, "ultimo_intento": None}
    hoy = hoy or datetime.datetime.now()
    ok = _parse_ts(r["ultimo_ok"])
    horas = (hoy - ok).total_seconds() / 3600 if ok else None
    pend = r["pendientes"] or 0
    stale = pend > 0 and (horas is None or horas > umbral)
    return {"conocido": True, "stale": stale, "pendientes": pend, "muro": bool(r["muro"]),
            "horas": round(horas, 1) if horas is not None else None,
            "ultimo_ok": r["ultimo_ok"], "ultimo_intento": r["ultimo_intento"]}


def _parse_ts(s):
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(str(s)[:19])
    except ValueError:
        return None


def una_pasada(descargar=_descargar_real, analizar=_analizar_real, con_capac=None):
    """Una pasada completa: descarga (Capa B) y, si con_capac, análisis (Capa C). Deja heartbeat.
    con_capac=None lee LOVEO_WORKER_CAPAC (default ON; '0' lo apaga)."""
    schema_v3.migrate()  # cacheado por base: barato. Garantiza analisis_bases para pendientes_capac.
    if con_capac is None:
        con_capac = os.environ.get("LOVEO_WORKER_CAPAC", "1") != "0"
    cods = pendientes()
    bajadas, muro = 0, False
    for cod in cods:
        r = procesar(cod, descargar)
        bajadas += 1 if r["ok"] else 0
        muro = muro or r["muro"]
    analizadas = 0
    if con_capac:
        for cod in pendientes_capac():
            if procesar_capac(cod, analizar):
                analizadas += 1
    registrar_salud(len(cods), bajadas, analizadas, muro)
    return {"pendientes": len(cods), "procesadas": bajadas, "capac": analizadas}


def loop(descargar=_descargar_real, intervalo=None):
    intervalo = intervalo or int(os.environ.get("LOVEO_WORKER_INTERVAL", "120"))
    print(f"[worker] arrancando. backend={db.backend()} · intervalo={intervalo}s")
    while True:
        try:
            r = una_pasada(descargar)
            print(f"[worker] bajadas {r['procesadas']}/{r['pendientes']} · Capa C {r['capac']}. "
                  f"Durmiendo {intervalo}s.")
        except Exception as e:  # el loop nunca debe morir por un error puntual
            print(f"[worker] error en la pasada (sigo): {e}")
        time.sleep(intervalo)


if __name__ == "__main__":
    import sys
    if "--once" in sys.argv:
        print(una_pasada())
    else:
        loop()
