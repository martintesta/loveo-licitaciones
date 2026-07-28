"""
test_plan.py — Sensor del motor "Plan del día" / próxima mejor acción (epic plan-del-dia, Fase 1).

plan.construir compone las señales del `lics` de build_data en una cola priorizada de acciones.
Puro (dicts → acciones), sin DB.

  python -m pytest tests/test_plan.py -q
"""
import plan


def _lic(cod, **kw):
    base = {"cod": cod, "nom": "Lic " + cod, "org": "Muni X", "regc": "Maule",
            "estRev": "nueva", "estRes": None, "score": 80, "evDims": 6, "nDims": 6,
            "tri": "Priorizar", "dias": None, "diasVisita": None, "analisis": None, "dims": []}
    base.update(kw)
    return base


def _plan(*lics, **kw):
    return plan.construir({l["cod"]: l for l in lics}, **kw)


def test_visita_proxima_manda_sobre_una_nueva_lejana():
    # A: visita mañana (crítica). B: nueva fit sin deadline. A debe ir primero y ser tipo VISITA.
    a = _lic("A", diasVisita=1, estRev="aprobada", score=70)
    b = _lic("B", tri="Priorizar", score=95)
    res = _plan(a, b)
    assert res[0]["codigo"] == "A" and res[0]["tipo"] == "VISITA"
    assert "mañana" in res[0]["motivo"]


def test_accion_segun_estado_al_cerrar_pronto():
    aprob = _lic("AP", estRev="aprobada", dias=3)
    conbases = _lic("CB", estRev="en_revision", dias=3, analisis={"ts": "x"},
                    dims=[{"n": "Margen", "ev": False}])
    nueva = _lic("NU", estRev="nueva", dias=3)
    tipos = {a["codigo"]: a["tipo"] for a in _plan(aprob, conbases, nueva)}
    assert tipos == {"AP": "PRESENTAR", "CB": "CUBICAR", "NU": "REVISAR"}


def test_nueva_fit_sin_deadline_es_revisar_de_menor_prioridad():
    urgente = _lic("U", dias=2, estRev="nueva", score=60)          # cierra en 2
    tranqui = _lic("T", tri="Priorizar", score=95)                 # nueva valiosa, sin deadline
    res = _plan(urgente, tranqui)
    assert res[0]["codigo"] == "U"                                 # el deadline manda sobre el valor
    assert {a["tipo"] for a in res} == {"REVISAR"}


def test_cubicar_pendiente_sin_deadline():
    l = _lic("C", estRev="aprobada", analisis={"ts": "x"}, dims=[{"n": "Margen", "ev": False}])
    res = _plan(l)
    assert res and res[0]["tipo"] == "CUBICAR"


def test_excluye_descartadas_y_presentadas():
    d = _lic("D", estRev="descartada", dias=1)
    p = _lic("P", estRes="presentada", dias=1)
    g = _lic("G", estRes="ganada")
    assert _plan(d, p, g) == []


def test_sin_accion_si_nada_pendiente():
    # aprobada, sin deadline, con margen ya hecho → no hay nada que sugerir
    l = _lic("X", estRev="aprobada", tri="Priorizar", analisis={"ts": "x"},
             dims=[{"n": "Margen", "ev": True}])
    assert _plan(l) == []


def test_prioridad_pondera_valor_y_confianza():
    # dos visitas mismo día: la de mayor score×confianza va primero
    alto = _lic("H", diasVisita=2, score=100, evDims=6, nDims=6)
    bajo = _lic("L", diasVisita=2, score=100, evDims=3, nDims=6)   # misma nota, mitad de confianza
    res = _plan(alto, bajo)
    assert [a["codigo"] for a in res] == ["H", "L"]


def test_bases_para_seguida_sin_analizar():
    # la seguís (en_revision, score bueno) pero sin bases → acción BASES (conseguí las bases)
    l = _lic("B", estRev="en_revision", tri="Priorizar", analisis=None)
    res = _plan(l)
    assert res and res[0]["tipo"] == "BASES" and "bases" in res[0]["motivo"].lower()


def test_excluye_cierre_ya_pasado():
    l = _lic("V", estRev="nueva", tri="Priorizar", dias=-2)   # ya cerró
    assert _plan(l) == []


def test_visita_ya_pasada_no_es_accionable():
    # diasVisita negativo (la hora ya pasó, lo marca build_data) → no genera VISITA
    l = _lic("P", estRev="aprobada", diasVisita=-1, dias=20)
    res = _plan(l)
    assert not any(a["tipo"] == "VISITA" for a in res)


def test_limite():
    lics = [_lic(f"C{i}", dias=1) for i in range(20)]
    assert len(_plan(*lics, limite=5)) == 5
