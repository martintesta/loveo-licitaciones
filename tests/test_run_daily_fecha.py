"""
test_run_daily_fecha.py — El cron barre AYER, no hoy.

El bug: `run_daily.py` sin argumentos barría `time.strftime('%d%m%Y')` = hoy, y el cron corre a
las 08:00. A esa hora Mercado Público todavía no publicó casi nada, así que los runs quedaban con
3, 4 y 16 licitaciones contra las 1.142, 1.385 y 1.201 que la API devuelve para esos mismos días
una vez cerrados. Cada corrida diaria fabricaba un día "sospechoso" nuevo, y el auto-curador
—que recupera 3 por corrida— estaba apagando incendios que el propio cron encendía.

  python -m pytest tests/test_run_daily_fecha.py -q
"""
import time
import datetime

import run_daily


def test_el_default_del_cron_es_ayer():
    ayer = datetime.date.today() - datetime.timedelta(days=1)
    assert run_daily._ayer() == ayer.strftime("%d%m%Y")


def test_no_barre_el_dia_en_curso():
    """Lo que rompía: hoy todavía se está publicando, barrerlo garantiza un total absurdo."""
    assert run_daily._ayer() != time.strftime("%d%m%Y")


def test_cruza_bien_el_fin_de_mes(monkeypatch):
    """1-ago a las 08:00 tiene que barrer el 31-jul, no el 1-jul ni el 1-ago."""
    primero_agosto = time.mktime(datetime.datetime(2026, 8, 1, 8, 0).timetuple())
    monkeypatch.setattr(run_daily.time, "time", lambda: primero_agosto)
    assert run_daily._ayer() == "31072026"
