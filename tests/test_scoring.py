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


# =========================== base única: Pirque ============================

def test_la_distancia_se_mide_desde_la_base_activa_no_desde_la_mas_cercana():
    """INSTRUCCIÓN DE MARTÍN (ago-2026): el traslado se calcula SIEMPRE desde Pirque.

    Antes `_dist_min` tomaba la base MÁS CERCANA de las dos, lo que supone que el módulo puede
    salir indistintamente de Pirque o de Puerto Montt. Con la fabricación en un solo lugar eso
    subestima el flete, que es la partida que más varía entre una licitación cerca y una lejos:
    Los Lagos daba 30 km (Puerto Montt) y en realidad son 1.000 desde Pirque."""
    km_pirque, base = scoring._dist_min("Región de los Lagos", base="Pirque")
    assert base == "Pirque" and km_pirque == 1000
    km_pm, base_pm = scoring._dist_min("Región de los Lagos", base="Puerto Montt")
    assert base_pm == "Puerto Montt" and km_pm == 30


def test_magallanes_desde_pirque_dispara_la_penalizacion():
    sc, nota, trigger = scoring._logistico("Región de Magallanes y de la Antártica", "Punta Arenas")
    assert trigger is True and sc == 1
    assert "Pirque" in nota


def test_la_region_metropolitana_sigue_siendo_cerca():
    sc, nota, trigger = scoring._logistico("Región Metropolitana de Santiago", "Recoleta")
    assert trigger is False and sc == 9
