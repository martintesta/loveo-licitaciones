"""
test_observabilidad.py — Sensor de la captura de errores (endurecer operación, #5).

capturar() registra el traceback en la tabla `errores` y NUNCA lanza; recientes()/resolver()
alimentan el panel. SQLite temporal, sin Sentry (SENTRY_DSN ausente).

  python -m pytest tests/test_observabilidad.py -q
"""
import db
import observabilidad
import schema_v3


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    db.init_db()
    schema_v3.migrate()


def test_capturar_registra_con_traceback(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    try:
        raise ValueError("algo explotó")
    except ValueError as e:
        observabilidad.capturar("worker", e)
    es = observabilidad.recientes()
    assert len(es) == 1
    assert es[0]["contexto"] == "worker"
    assert "algo explotó" in es[0]["mensaje"]
    assert "ValueError" in es[0]["traceback"]   # el traceback quedó guardado


def test_capturar_con_mensaje_sin_excepcion(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    observabilidad.capturar("run_daily", mensaje="fuente caída")
    assert observabilidad.recientes()[0]["mensaje"] == "fuente caída"


def test_capturar_nunca_lanza(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    # incluso con una base rota, capturar no debe propagar (la observabilidad no tumba el flujo)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "nope" / "no.db")
    observabilidad.capturar("app", RuntimeError("x"))   # no explota


def test_resolver_saca_del_panel(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    observabilidad.capturar("app", mensaje="e1")
    observabilidad.capturar("app", mensaje="e2")
    eid = observabilidad.recientes()[0]["id"]
    observabilidad.resolver(eid)
    ids = [e["id"] for e in observabilidad.recientes()]
    assert eid not in ids and len(ids) == 1
    assert len(observabilidad.recientes(incluir_resueltos=True)) == 2


def test_init_sin_dsn_es_noop(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert observabilidad.init() is False
