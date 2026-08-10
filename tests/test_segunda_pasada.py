"""
test_segunda_pasada.py — Sensor del rescate de licitaciones que el título esconde.

El listado diario del API trae SOLO {CodigoExterno, Nombre, CodigoEstado, FechaCierre}. Una
licitación cuyo producto aparece únicamente en la descripción no llega jamás al filtro. Caso real
y caro: "ADQUIS E INST PUNTO DE SEGURIDAD AMERICO VESPUCIO" (Recoleta, $15,0M) era un container
habilitado como oficina modular. La encontró Martín a mano, no la herramienta.

  python -m pytest tests/test_segunda_pasada.py -q
"""
import discover


def _item(nombre, cod="X-1-LE26"):
    return {"CodigoExterno": cod, "Nombre": nombre, "CodigoEstado": 5,
            "FechaCierre": "2026-08-20T15:00:00"}


def test_el_caso_recoleta_entra_a_la_segunda_pasada():
    """El título no dice container, módulo ni modular. Tiene que sobrevivir el filtro barato
    para que se le pida el detalle: es la única vía por la que esta licitación puede entrar."""
    listado = [_item("ADQUIS E INST PUNTO DE SEGURIDAD AMERICO VESPUCIO", "1431841-49-LE26")]
    cands = discover.candidatas_segunda_pasada(listado)
    assert [x["CodigoExterno"] for x in cands] == ["1431841-49-LE26"]


def test_lo_que_ya_matchea_por_titulo_no_se_pide_de_nuevo():
    """No gastar una llamada de API en algo que ya entró por la vía barata."""
    listado = [_item("ADQUISICION DE CONTAINERS PARA SALUD", "2766-118-LE26")]
    assert discover.candidatas_segunda_pasada(listado) == []


def test_el_ruido_evidente_no_gasta_una_llamada():
    """Muestra real del listado del día: nada de esto amerita pedir el detalle."""
    ruido = ["SUMINISTRO DE MAMADERAS PARA LA UNIDAD DE SEDILE",
             "ADQUISICIÓN DE LEÑA PARA LOS ESTABLECIMIENTOS",
             "Compra por Suministro de Marcapasos Multiprogramables",
             "CONVENIO SUMINISTRO DE OXÍGENO MEDICINAL SAMU",
             "ADQUISICIÓN DE CORTINAS Y EMPAVONADO NUEVO SML STG"]
    listado = [_item(n, f"R-{i}-LE26") for i, n in enumerate(ruido)]
    assert discover.candidatas_segunda_pasada(listado) == []


def test_sin_verbo_de_compra_no_entra():
    """Un título sin verbo de compra rara vez es un bien: no vale la llamada."""
    listado = [_item("SERVICIO DE ASESORÍA JURÍDICA ANUAL", "S-1-LE26")]
    assert discover.candidatas_segunda_pasada(listado) == []


def test_no_repite_las_ya_matcheadas_por_codigo():
    listado = [_item("ADQUISICION E INSTALACION DE PUNTO LIMPIO", "Y-1-LE26")]
    assert discover.candidatas_segunda_pasada(listado, ya_matcheadas={"Y-1-LE26"}) == []


def test_el_filtro_barato_recorta_de_verdad():
    """Sobre el listado real de 1.186 licitaciones el filtro deja 337 (28%). Acá se fija que
    el ruido recorte: si dejara pasar todo, la segunda pasada costaría 1.186 llamadas."""
    # el primer grupo NO tiene keyword de producto en el título (por eso es candidato de 2ª
    # pasada); el segundo es ruido; el tercero no tiene verbo de compra.
    listado = ([_item("ADQUISICION E INSTALACION PUNTO DE ATENCION VECINAL", f"A-{i}-LE26")
                for i in range(10)] +
               [_item("ADQUISICION DE MEDICAMENTOS ONCOLOGICOS", f"B-{i}-LE26") for i in range(10)] +
               [_item("SERVICIO DE VIGILANCIA PERMANENTE", f"C-{i}-LE26") for i in range(10)])
    cands = discover.candidatas_segunda_pasada(listado)
    assert len(cands) == 10


def test_lo_que_ya_entra_por_titulo_queda_fuera_de_la_segunda_pasada():
    """'ADQUISICION DE MODULO PARA ESCUELA' matchea por keyword: entra por la vía barata y no
    debe consumir presupuesto de llamadas."""
    listado = [_item("ADQUISICION DE MODULO PARA ESCUELA", "M-1-LE26")]
    assert discover.candidatas_segunda_pasada(listado) == []
