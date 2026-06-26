"""
test_manual_add.py — Sensor de la alta manual por código (Fase 1, spec curaduria-aprendizaje).

Verifica la orquestación de run_daily.procesar_codigo SIN red: mockea la capa de
descubrimiento (traer_detalle / _aplanar_detalle) y la admisibilidad, deja correr el
scoring real, y comprueba que la lic queda insertada, con score y con el evento
'agregada_manual'. Todo contra SQLite temporal (no toca Neon).

  python -m pytest tests/test_manual_add.py -q
"""
import db
import discover
import rules
import run_daily


def _setup(monkeypatch, tmp_path, row):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(discover, "traer_detalle", lambda cod: {"_fake_detalle": cod})
    monkeypatch.setattr(discover, "_aplanar_detalle", lambda det: dict(row))
    monkeypatch.setattr(rules, "evaluar",
                        lambda r: {"admisible": True, "motivos": [], "vigente": True, "requiere_bases": False})


def test_alta_manual_inserta_con_score_y_evento(tmp_path, monkeypatch):
    _setup(monkeypatch, tmp_path, {
        "codigo": "MANUAL-1",
        "nombre": "Contenedor modular de prueba",
        "region": "Región Metropolitana de Santiago",
        "modalidad": 1,
    })
    r = run_daily.procesar_codigo("MANUAL-1")
    assert r["ok"] is True
    assert r["codigo"] == "MANUAL-1"
    assert r["admisible"] is True
    assert r["score"] is not None  # admisible + región => hay score provisional
    assert r["ya_existia"] is False

    with db.conn() as c:
        lic = c.execute("SELECT codigo, score_provisional FROM licitaciones WHERE codigo=?",
                        ("MANUAL-1",)).fetchone()
        ev = c.execute("SELECT 1 FROM eventos WHERE codigo=? AND tipo='agregada_manual'",
                       ("MANUAL-1",)).fetchone()
    assert lic["codigo"] == "MANUAL-1"
    assert lic["score_provisional"] is not None
    assert ev is not None  # trazabilidad de la alta manual


def test_alta_manual_codigo_vacio():
    assert run_daily.procesar_codigo("   ")["ok"] is False


def test_alta_manual_sin_datos(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(discover, "traer_detalle", lambda cod: None)  # MP no devuelve nada
    r = run_daily.procesar_codigo("NO-EXISTE-1")
    assert r["ok"] is False
    assert "no devolvió" in r["error"].lower() or "revis" in r["error"].lower()
