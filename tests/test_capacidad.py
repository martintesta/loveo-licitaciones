"""
test_capacidad.py — La cuadrilla es el recurso escaso, y eso decide el GO/NO-GO.

EL CASO QUE ORIGINA TODO ESTO: Talagante cerró con +$12.000.000 de contribución — más del doble
que Vicuña, el segundo mejor del año — y fue el peor negocio. Ocupó 120 días-cuadrilla de los
~250 que tiene el año, o sea $100.000 por día contra un piso de $192.000. Ninguna métrica de
margen porcentual ve eso: por margen, Talagante era el mejor proyecto de la historia de Loveo.

  python -m pytest tests/test_capacidad.py -q
"""
import pytest

import costos_parametricos as cp

# Los cinco proyectos ejecutados con costo REAL conocido, y si pagaron o no la estructura.
# (nombre, ingreso, costo_real, días-cuadrilla estimados, ¿pagó los $192.000/día?)
EJECUTADOS = [
    ("Vicuña",           30_252_101, 24_544_067, 14, True),
    ("Coquimbo",         17_000_000, 13_867_023, 14, True),
    ("Chiloé-Castro",    14_000_000, 11_437_529, 14, False),
    ("Maipú",            15_000_000, 13_632_345, 14, False),
    ("Diego de Almagro", 16_900_000, 16_211_267, 14, False),
]


def test_el_piso_sale_de_la_estructura_no_de_una_opinion():
    """$4.000.000/mes × 12 ÷ 250 días-cuadrilla = $192.000. No hay número elegido a gusto."""
    assert cp.costo_fijo_por_dia() == pytest.approx(192_000, abs=1)


def test_los_subcontratos_no_compran_capacidad():
    """Una cuadrilla de 3 personas va a TODO proyecto; subcontratar escala oficios, no días."""
    assert cp.CUADRILLAS == 1
    assert cp.DIAS_HABILES_ANO == 250


@pytest.mark.parametrize("nombre,ingreso,costo,dias,paga", EJECUTADOS)
def test_clasifica_bien_los_proyectos_ejecutados(nombre, ingreso, costo, dias, paga):
    """El costo real ya trae el sobrecosto incorporado, así que se pasa como base neta."""
    base = costo / (1 + cp.SOBRECOSTO_MEDIDO)
    v = cp.veredicto_capacidad(ingreso, base, dias, costo_ya_neto=True)
    assert (v["por_dia"] >= v["piso_dia"]) is paga, (
        f"{nombre}: ${v['por_dia']:,}/día contra piso ${v['piso_dia']:,}")
    if not paga:
        assert v["veredicto"] == "NO-GO"


def test_talagante_gana_por_margen_y_pierde_por_ocupacion():
    """EL caso. Mayor contribución absoluta del año, peor negocio del año."""
    contribucion, dias = 12_000_000, 120
    por_dia = contribucion / dias
    piso = cp.costo_fijo_por_dia()

    # gana por tamaño: más que ningún otro proyecto
    mejor_normal = max(i - c for _, i, c, _, _ in EJECUTADOS)
    assert contribucion > 2 * mejor_normal

    # y pierde por ocupación
    assert por_dia < piso
    assert (por_dia - piso) * dias == pytest.approx(-11_040_000, abs=1000)


def test_las_señales_de_talagante_reproducen_sus_120_dias():
    """Fabricación en sitio, obras civiles, traslado múltiple y terminaciones en destino sobre un
    módulo clínico. Si el estimador no reprodujera el caso que lo motivó, no serviría de nada."""
    d = cp.dias_cuadrilla("modulo_clinico", 1,
                          ("fabricacion_en_sitio", "obras_civiles",
                           "traslado_multiple", "terminaciones_destino"))
    assert 110 <= d <= 140, f"estimó {d} días contra los 120 reales"


def test_un_modulo_normal_cae_en_la_ventana_medida():
    """Martín: 8-22 días, promedio 8-15. Sin señales, ningún tipo puede escaparse de ahí."""
    for tipo in cp.DIAS_BASE:
        d = cp.dias_cuadrilla(tipo, 1)
        assert 8 <= d <= 22, f"{tipo}: {d} días, fuera de lo medido"


def test_el_mismo_margen_con_mas_dias_vale_menos():
    """La consecuencia práctica: dos proyectos idénticos en plata, distinto en días, no son
    igual de buenos. Es justo lo que el margen porcentual no distingue."""
    rapido = cp.veredicto_capacidad(20_000_000, 10_000_000, 10, costo_ya_neto=True)
    lento = cp.veredicto_capacidad(20_000_000, 10_000_000, 40, costo_ya_neto=True)
    assert rapido["contribucion"] == lento["contribucion"]      # misma plata
    assert rapido["por_dia"] > 4 * lento["por_dia"] * 0.9       # muy distinto negocio


def test_la_banda_ajustado_es_la_que_no_aguanta_un_sigma():
    """AJUSTADO no es 'mediano': es 'pasa en el caso base y se cae con el error de estimación
    que ya medimos' (σ = 0,14 sobre el costo)."""
    v = cp.veredicto_capacidad(30_252_101, 24_544_067 / (1 + cp.SOBRECOSTO_MEDIDO), 14,
                               costo_ya_neto=True)
    assert v["veredicto"] == "AJUSTADO"
    assert v["por_dia"] >= v["piso_dia"] > v["por_dia_conservador"]


def test_un_margen_muy_por_encima_del_record_se_marca_como_sospechoso():
    """Las cuatro que dieron GO FUERTE implicaban 33-45% operativo, entre 1,7 y 2,4 veces el
    récord de Loveo. La lectura probable no es 'gran negocio' sino 'falta una partida'."""
    sosp, motivo = cp.demasiado_bueno(85_618_185, 47_451_111 / (1 + cp.SOBRECOSTO_MEDIDO),
                                      costo_ya_neto=True)
    assert sosp and "récord" in motivo


def test_un_proyecto_real_no_se_marca_como_sospechoso():
    """Vicuña, que ES el récord, no puede disparar la alarma."""
    sosp, _ = cp.demasiado_bueno(30_252_101, 24_544_067 / (1 + cp.SOBRECOSTO_MEDIDO),
                                 costo_ya_neto=True)
    assert not sosp
