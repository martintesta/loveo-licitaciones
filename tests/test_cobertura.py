"""
test_cobertura.py — El barrido se audita a sí mismo.

Un día hábil que no se procesó (o que se procesó con la API caída) es INVISIBLE: no hay error,
no hay alerta, esas licitaciones simplemente nunca existieron para el sistema. Se descubrió
cruzando contra un registro externo: 62 licitaciones faltantes, 5 días procesados de ~40.
Este sensor existe para que ese cruce no vuelva a hacer falta.

  python -m pytest tests/test_cobertura.py -q
"""
import datetime

import cobertura
import db


def _setup(tmp_path, monkeypatch, runs=()):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    with db.conn() as c:
        for fecha, total in runs:
            db.record_run(c, fecha, total, 0, 0, 0)


def _viernes():
    """Un lunes fijo como 'hoy' para que la ventana hábil sea determinística."""
    return datetime.date(2026, 8, 3)      # lunes


def test_dia_habil_sin_corrida_es_un_hueco(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    e = cobertura.estado(dias=5, hoy=_viernes())
    assert e["esperados"] == 5 and e["procesados"] == 0
    assert len(e["faltantes"]) == 5 and e["pct"] == 0.0


def test_dia_procesado_en_falso_no_cuenta_como_cubierto(tmp_path, monkeypatch):
    """EL bug que causó todo: el 13/07 registró total_dia=1 (la API falló) y quedó marcado como
    'procesado', así que un backfill ingenuo lo saltearía PARA SIEMPRE."""
    habiles = cobertura._habiles(5, _viernes())
    _setup(tmp_path, monkeypatch, runs=[(habiles[0], 1)])     # corrida con 1 sola licitación
    e = cobertura.estado(dias=5, hoy=_viernes())
    assert habiles[0] in e["sospechosos"]                     # detectado, no dado por bueno
    assert habiles[0] not in e["faltantes"]
    assert e["procesados"] == 0                               # NO cuenta como cubierto
    # entra en la cola de recuperación (después de los faltantes, que nunca se vieron)
    assert habiles[0] in cobertura.a_reprocesar(9, dias=5, hoy=_viernes())


def test_dia_con_barrido_real_cuenta_como_cubierto(tmp_path, monkeypatch):
    habiles = cobertura._habiles(5, _viernes())
    _setup(tmp_path, monkeypatch, runs=[(f, 1000) for f in habiles])
    e = cobertura.estado(dias=5, hoy=_viernes())
    assert e["procesados"] == 5 and e["huecos"] == 0 and e["pct"] == 100.0
    assert cobertura.a_reprocesar(3, dias=5, hoy=_viernes()) == []


def test_no_audita_el_dia_en_curso(tmp_path, monkeypatch):
    """Hoy todavía se está publicando: no se puede juzgar su cobertura."""
    hoy = _viernes()
    assert hoy.strftime("%d%m%Y") not in cobertura._habiles(10, hoy)


def test_ignora_fines_de_semana(tmp_path, monkeypatch):
    for f in cobertura._habiles(10, _viernes()):
        d = datetime.datetime.strptime(f, "%d%m%Y").date()
        assert d.weekday() < 5, f"{f} cae fin de semana"


def test_dia_genuinamente_flaco_deja_de_reintentarse(tmp_path, monkeypatch):
    """16/07/2026 tiene 9 publicaciones y la API devuelve 9 cada vez. Sin memoria de reintentos,
    el curador lo rebarre TODAS las mañanas para siempre y nunca cambia nada."""
    habiles = cobertura._habiles(5, _viernes())
    flaco = habiles[0]
    _setup(tmp_path, monkeypatch, runs=[(f, 1000) for f in habiles[1:]])
    with db.conn() as c:
        for _ in range(cobertura.MAX_REINTENTOS + 1):     # barrido inicial + los reintentos
            db.record_run(c, flaco, 9, 0, 0, 0)

    e = cobertura.estado(dias=5, hoy=_viernes())
    assert flaco in e["confirmados_flacos"]
    assert flaco not in e["sospechosos"]
    assert e["huecos"] == 0                                # deja de contar como agujero
    assert cobertura.a_reprocesar(5, dias=5, hoy=_viernes()) == []


def test_un_rebarrido_que_recupera_datos_resetea_los_reintentos(tmp_path, monkeypatch):
    """Lo contrario: si el rebarrido SÍ trae más, el día se curó — no hay que darlo por flaco."""
    habiles = cobertura._habiles(5, _viernes())
    dia = habiles[0]
    _setup(tmp_path, monkeypatch, runs=[(f, 1000) for f in habiles[1:]])
    with db.conn() as c:
        for _ in range(cobertura.MAX_REINTENTOS + 1):
            db.record_run(c, dia, 4, 0, 0, 0)             # el cron barriendo el día a medio publicar
        db.record_run(c, dia, 1385, 12, 12, 0)            # rebarrido con el día ya cerrado
        r = c.execute("SELECT reintentos FROM runs WHERE fecha=?", (dia,)).fetchone()

    assert r["reintentos"] == 0
    e = cobertura.estado(dias=5, hoy=_viernes())
    assert e["procesados"] == 5 and e["huecos"] == 0


def test_los_faltantes_se_recuperan_antes_que_los_sospechosos(tmp_path, monkeypatch):
    """Prioridad: lo que nunca se vio pesa más que lo que se vio mal."""
    habiles = cobertura._habiles(5, _viernes())
    _setup(tmp_path, monkeypatch, runs=[(habiles[0], 1)] + [(f, 1000) for f in habiles[2:]])
    orden = cobertura.a_reprocesar(5, dias=5, hoy=_viernes())
    assert orden[0] == habiles[1]        # el faltante primero
    assert habiles[0] in orden           # el sospechoso también, pero después
