"""
worker.py — Worker residencial (Capa B: descarga de bases + futura Ficha Comprador).

POR QUÉ EXISTE: el endpoint de adjuntos de Mercado Público y la Ficha Comprador bloquean
accesos automatizados de datacenter (403 / captcha). La UI hosteada (Render) NO hace esto;
solo este worker, que corre en una máquina con IP CHILENA RESIDENCIAL (tu notebook prendido).

QUÉ HACE: hace polling de la MISMA base (DATABASE_URL → Neon), busca licitaciones admisibles
con docs_estado='pendiente', baja sus bases reusando download.descargar_codigo (Capa B), y
marca el resultado. Ver WORKER.md para el deploy.

  python worker.py            # loop infinito (intervalo LOVEO_WORKER_INTERVAL seg; default 120)
  python worker.py --once     # una sola pasada y termina

La descarga real (Playwright) vive en download.py y se importa PEREZOSAMENTE: así el loop se
puede testear sin Playwright ni IP chilena (inyectando una función de descarga mock).
"""
import os
import time

import db


def pendientes(limit=20):
    """Licitaciones admisibles con bases sin bajar (mismo criterio que download.pendientes)."""
    with db.conn() as c:
        return [r[0] for r in c.execute(
            "SELECT codigo FROM licitaciones WHERE admisible=1 AND docs_estado='pendiente' "
            "ORDER BY fecha_actualizada DESC LIMIT ?", (limit,)).fetchall()]


def procesar(codigo, descargar):
    """Procesa UNA licitación con la función de descarga inyectada (real o mock).

    La descarga real (download.descargar_codigo) maneja su propio docs_estado (descargando→
    descargado). Acá solo cubrimos el caso de EXCEPCIÓN: marcar 'error' + dejar traza.
    Devuelve True si la descarga no lanzó excepción.
    """
    try:
        return bool(descargar(codigo))
    except Exception as e:
        with db.conn() as c:
            # no pisar un 'descargado' exitoso si la excepción llegó tarde
            c.execute("UPDATE licitaciones SET docs_estado='error' "
                      "WHERE codigo=? AND docs_estado!='descargado'", (codigo,))
            db.log_evento(c, codigo, "error", f"worker: descarga falló: {e}")
        return False


def _descargar_real(codigo):
    # Import perezoso: download.py trae Playwright, que NO hace falta para testear el loop.
    import download
    return download.descargar_codigo(codigo)


def ficha_comprador(organismo):
    """TODO (worker residencial): leer la Ficha Comprador — comportamiento de pago del
    comprador (quejas de no-pago a tiempo), detrás del WAF de www.mercadopublico.cl
    (403/captcha desde datacenter). Alimentaría la señal 'mal_pagador' del aprendizaje y el
    cash flow del score. Pendiente de calibración local (ver WORKER.md)."""
    raise NotImplementedError("Ficha Comprador: pendiente del worker residencial. Ver WORKER.md.")


def una_pasada(descargar=_descargar_real):
    cods = pendientes()
    hechas = sum(1 for cod in cods if procesar(cod, descargar))
    return {"pendientes": len(cods), "procesadas": hechas}


def loop(descargar=_descargar_real, intervalo=None):
    intervalo = intervalo or int(os.environ.get("LOVEO_WORKER_INTERVAL", "120"))
    print(f"[worker] arrancando. backend={db.backend()} · intervalo={intervalo}s")
    while True:
        try:
            r = una_pasada(descargar)
            print(f"[worker] {r['procesadas']}/{r['pendientes']} procesadas. Durmiendo {intervalo}s.")
        except Exception as e:  # el loop nunca debe morir por un error puntual
            print(f"[worker] error en la pasada (sigo): {e}")
        time.sleep(intervalo)


if __name__ == "__main__":
    import sys
    if "--once" in sys.argv:
        print(una_pasada())
    else:
        loop()
