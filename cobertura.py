"""
cobertura.py — El sistema audita SU PROPIO barrido: qué días hábiles no procesó y cuáles procesó mal.

Sin esto, un día perdido es invisible: no hay error, no hay alerta, simplemente esas licitaciones
nunca existieron para el sistema. Se detectó cruzando contra un registro externo (62 licitaciones
faltantes, 5 días procesados de ~40). El objetivo de este módulo es que ese cruce no haga falta:
la única fuente de verdad sobre la cobertura es el propio sistema.

Dos tipos de agujero:
  FALTANTE   día hábil sin ninguna corrida registrada.
  SOSPECHOSO día con corrida pero un total absurdamente bajo — la API falló (429/timeout) y quedó
             marcado como "procesado", así que un backfill ingenuo lo saltearía para siempre.

  estado(dias)         -> resumen para la UI y para decidir si hay que curar
  a_reprocesar(limite) -> los días a (re)procesar, del más reciente al más viejo
"""
import datetime

import db

try:
    from config import COBERTURA_MIN_DIA as MIN_DIA
except (ImportError, AttributeError):
    MIN_DIA = 50        # un día hábil real trae ~1.000 licitaciones; menos que esto es corrida fallida
try:
    from config import COBERTURA_DIAS as DIAS_VENTANA
except (ImportError, AttributeError):
    DIAS_VENTANA = 30   # ventana hábil que se audita hacia atrás
try:
    from config import COBERTURA_CURAR_POR_CORRIDA as CURAR_POR_CORRIDA
except (ImportError, AttributeError):
    CURAR_POR_CORRIDA = 3   # días a recuperar por corrida diaria (cada uno es una llamada a la API)


def _habiles(dias, hoy=None):
    """Los últimos `dias` días HÁBILES (lun-vie) hacia atrás, en formato ddmmaaaa. Excluye hoy:
    el día en curso todavía se está publicando, no se puede juzgar su cobertura."""
    hoy = hoy or datetime.date.today()
    out, d = [], 1
    while len(out) < dias and d < dias * 3:
        f = hoy - datetime.timedelta(days=d)
        if f.weekday() < 5:
            out.append(f.strftime("%d%m%Y"))
        d += 1
    return out


def estado(dias=None, hoy=None):
    """Cobertura del barrido en la ventana: qué se procesó, qué falta y qué salió mal."""
    dias = DIAS_VENTANA if dias is None else dias
    esperados = _habiles(dias, hoy)
    with db.conn() as c:
        runs = {r["fecha"]: r["total_dia"] for r in
                c.execute("SELECT fecha, total_dia FROM runs").fetchall()}
    faltantes = [f for f in esperados if f not in runs]
    sospechosos = [f for f in esperados if f in runs and (runs[f] or 0) < MIN_DIA]
    ok = len(esperados) - len(faltantes) - len(sospechosos)
    return {
        "esperados": len(esperados),
        "procesados": ok,
        "faltantes": faltantes,
        "sospechosos": sospechosos,
        "huecos": len(faltantes) + len(sospechosos),
        "pct": round(100 * ok / len(esperados), 1) if esperados else 100.0,
    }


def a_reprocesar(limite=3, dias=None, hoy=None):
    """Días a (re)procesar, del más reciente al más viejo. Los faltantes primero (nunca se vieron),
    después los sospechosos (se vieron mal). Acotado: cada día es una llamada a la API."""
    e = estado(dias, hoy)
    return (e["faltantes"] + e["sospechosos"])[:limite]
