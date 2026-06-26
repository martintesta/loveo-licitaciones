"""
test_scoring.py — Sensor del scoring provisional (la lógica del triage).

Puro (sin DB ni red). Cubre la estructura del resultado y las invariantes de honestidad:
margen y complejidad NUNCA se evalúan con datos de API (quedan pendientes de bases/cubicación).

  python -m pytest tests/test_scoring.py -q
"""
import scoring

RM = "Región Metropolitana de Santiago"


def test_estructura_y_honestidad():
    sc = scoring.score_provisional({"nombre": "Contenedor modular", "region": RM, "modalidad": 1})
    assert sc["max"] == 120
    assert 0 <= sc["score_provisional"] <= 120
    assert sc["triage"] in ("Priorizar", "Revisar", "Descartar candidato")
    # Invariante: margen y complejidad no son evaluables desde la API.
    assert sc["dimensiones"]["margen"]["evaluado"] is False
    assert sc["dimensiones"]["complejidad"]["evaluado"] is False
    assert sc["requiere_bases"] is True


def test_alineacion_core_supera_territorio_nuevo():
    core = scoring.score_provisional({"nombre": "módulo modular", "region": RM, "modalidad": 1})
    nuevo = scoring.score_provisional({"nombre": "remodelación de plaza", "region": RM, "modalidad": 1})
    assert core["dimensiones"]["alineacion"]["score"] > nuevo["dimensiones"]["alineacion"]["score"]


def test_logistico_lejos_penaliza_y_dispara_x3():
    cerca = scoring.score_provisional({"nombre": "container", "region": RM, "modalidad": 1})
    lejos = scoring.score_provisional({"nombre": "container", "region": "Región de Magallanes", "modalidad": 1})
    assert lejos["dimensiones"]["logistico"]["score"] < cerca["dimensiones"]["logistico"]["score"]
    assert lejos["logistico_x3"] is True  # >300 km dispara el ×3 logístico


def test_cashflow_sin_modalidad_queda_pendiente():
    sc = scoring.score_provisional({"nombre": "container", "region": RM})  # sin modalidad
    assert sc["dimensiones"]["cashflow"]["evaluado"] is False
