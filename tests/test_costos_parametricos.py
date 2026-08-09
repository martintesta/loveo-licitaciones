"""
test_costos_parametricos.py — Sensor de la tabla de costo paramétrico del Gate 2.

Los números salen de proyectos GANADOS Y EJECUTADOS. Estos tests fijan las dos decisiones que
cambian el modelo financiero (margen sobre venta, sobrecosto medido) y la precisión exigible:
la tabla es un FILTRO, no una cotización — se le pide ordenar de magnitud, no exactitud.

  python -m pytest tests/test_costos_parametricos.py -q
"""
import costos_parametricos as cp


def test_el_margen_es_sobre_la_venta_no_sobre_el_costo():
    """Verificado con la planilla de Loveo: Vicuña, ingreso 30.252.101, costo real 24.544.067,
    'Margen Real %' = 0,1887 = (ingreso − costo)/ingreso."""
    m = cp.margenes(30_252_101, 24_544_067 / 1.304, margen_error=0)
    assert abs(m["margen_optimista"] - 0.1887) < 0.005


def test_el_sobrecosto_medido_es_el_30_por_ciento():
    """No era un colchón conservador: es el valor esperado. costo_real/costo_estimado = 1,304
    promedio sobre los 5 proyectos cerrados."""
    assert 0.28 <= cp.SOBRECOSTO_MEDIDO <= 0.32


def test_los_dos_metodos_se_comparan_y_la_divergencia_se_reporta():
    r = cp.estimar("modulo_estandar", "basico", n_modulos=2, m2=200, km=100)
    assert r["metodo_modulo"] and r["metodo_m2"]
    assert r["divergencia"] is not None
    assert r["costo_base_inconsistente"] is True      # 200 m² no calzan con 2 módulos
    assert r["costo_base"] == min(r["metodo_modulo"], r["metodo_m2"])   # manda el conservador


def test_sin_divergencia_no_se_marca_inconsistente():
    r = cp.estimar("modulo_estandar", "basico", n_modulos=2, km=100)
    assert r["costo_base_inconsistente"] is False


def test_el_flete_es_en_pesos_y_crece_con_la_distancia():
    """La partida que más varía entre una licitación cerca y una lejos. Convertirla a puntos
    1-9 tira justo la información que más pesa."""
    assert cp.flete(30) < cp.flete(400) < cp.flete(1100)
    assert cp.flete(30, 1) < cp.flete(30, 3)          # más módulos, más flete, pero no lineal
    assert cp.flete(None) is None


def test_semaforo_verde_amarillo_rojo():
    assert cp.margenes(100_000_000, 30_000_000)["semaforo"] == "verde"
    assert cp.margenes(100_000_000, 52_000_000)["semaforo"] == "amarillo"
    assert cp.margenes(100_000_000, 70_000_000)["semaforo"] == "rojo"


def test_descarta_solo_cuando_no_alcanza_ni_en_el_escenario_optimista():
    """Rojo es 'pasa con margen ajustado'. Descarte es 'no alcanza ni siendo optimista'."""
    assert cp.margenes(100_000_000, 70_000_000)["descarta"] is False
    assert cp.margenes(50_000_000, 60_000_000)["descarta"] is True


def test_precision_suficiente_para_filtrar_en_los_proyectos_reales():
    """Contra el costo REAL de 5 proyectos ejecutados: el error tiene que quedar dentro de ±30%.
    Con 5 puntos de datos no se puede pedir más, y para un filtro alcanza."""
    casos = [("modulo_estandar", "basico", 2, 470, 11_638_600),
             ("modulo_simple", "basico", 2, 90, 8_020_000),
             ("modulo_camarin", "sanitario", 2, 90, 11_398_200),
             ("modulo_estandar", "basico", 2, 900, 16_211_267)]
    for tipo, ac, n, km, real in casos:
        est = cp.estimar(tipo, ac, n, None, km)["costo_base"]
        assert abs(est - real) / real < 0.30, f"{tipo}: estimó {est} contra {real} real"
