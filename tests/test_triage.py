"""
test_triage.py — Sensor del embudo de filtros que reemplaza al score provisional.

Los cinco primeros son los casos de aceptación exigidos por el rediseño: son falsos positivos
REALES de agosto 2026, todos con score alto en el modelo viejo (dos con 84, el máximo del sistema).
Si alguno de esos vuelve a pasar, el embudo no sirve.

  python -m pytest tests/test_triage.py -q
"""
from datetime import datetime, timedelta

import triage


def _lic(nombre, descripcion="", **kw):
    return {"nombre": nombre, "descripcion": descripcion, **kw}


def _con_onu(nombre, familia, descripcion="", **kw):
    detalle = {"Items": {"Listado": [{"CodigoCategoria": familia + "1500",
                                      "Categoria": "cat de prueba"}]}}
    import json
    return _lic(nombre, descripcion, json_detalle=json.dumps(detalle), **kw)


# =========================== ACEPTACIÓN: los 5 =============================

def test_acepta_1_software_no_pasa():
    """Sacaba 84, el máximo del sistema viejo, por la palabra 'modular'."""
    r = triage.gate_producto(_lic(
        "CONTRATACIÓN DEL DESARROLLO DE LA PLATAFORMA MODULAR DE COMPRAS",
        "Desarrollo de la plataforma modular de compras para la Dirección de Compras Públicas."))
    assert r["pasa"] is False


def test_acepta_2_juegos_infantiles_no_pasan():
    """El otro 84."""
    r = triage.gate_producto(_lic(
        "ADQUISICION E INSTALACION DE 7 JUEGOS MODULARES PARA RECUPERACION DE ESPACIOS PUBLICOS",
        "Instalación de juegos modulares de alto tráfico para esparcimiento de niños."))
    assert r["pasa"] is False


def test_acepta_3_contenedores_refrigerados_no_pasan():
    r = triage.gate_producto(_lic(
        "ADQUISICION DE CONTENEDORES REFRIGERADOS",
        "Adquirir contenedores refrigerados para transporte estratégico antártico."))
    assert r["pasa"] is False


def test_acepta_4_carroceria_no_pasa():
    r = triage.gate_producto(_lic(
        "ADQUISICIÓN DE CONTENEDOR OPEN TOP 15M3 PARA CAMION CON POLIBRAZO",
        "Contenedor open top para camión con polibrazo."))
    assert r["pasa"] is False


def test_acepta_5_leche_en_polvo_no_pasa():
    r = triage.gate_producto(_lic(
        "MÓDULO NUTRICIONAL EN POLVO",
        "Adquisición de fórmulas lácteas y alimentos en polvo para el programa nutricional."))
    assert r["pasa"] is False


# =========================== no romper lo bueno ============================

def test_el_contenedor_de_oficina_si_pasa():
    r = triage.gate_producto(_lic(
        "Adquisicion de contenedores",
        "Siete contenedores marítimos habilitados como módulos de oficina."))
    assert r["pasa"] is True and r["senal"] == "core"


def test_la_sala_reas_si_pasa():
    r = triage.gate_producto(_lic("CONSTRUCCION SALA REAS", "Sala de residuos hospitalarios."))
    assert r["pasa"] is True


def test_box_dental_pasa():
    r = triage.gate_producto(_lic("MEJORAMIENTO BOX DENTAL CECOSF",
                                  "Reposición del box dental del CECOSF."))
    assert r["pasa"] is True


def test_sede_modular_pasa_por_coexistencia():
    """'modular' junto a un objeto físico: es lo que separa una sede de una plataforma."""
    r = triage.gate_producto(_lic("ADQUISICION DE SEDES MODULARES COMUNITARIAS",
                                  "Adquisición, transporte e instalación de sedes modulares."))
    assert r["pasa"] is True and r["senal"] == "coexistencia"


def test_modular_solo_pasa_pero_a_revision():
    """POLÍTICA REVISADA tras auditar contra las decisiones reales: 'modular' sin objeto físico
    NO mata. Mataba 'MODULOS ADMINISTRATIVOS PARA HOSPITAL CARAHUE' y 'Unidades Modulares para
    la EMR de Perales', dos licitaciones que Loveo sí quería. Un falso positivo cuesta una
    licitación; un falso negativo cuesta horas. Con esa asimetría, la duda deja pasar y se marca.
    El software muere igual, pero por su negativa dura ('plataforma'), no por ausencia de señal."""
    r = triage.gate_producto(_lic("Servicio modular de gestión documental", "Gestión documental."),
                             excluir=[])
    assert r["pasa"] is True and r["senal"] == "modular_suelto" and r["confianza"] == "baja"


# =========================== familia ONU ===================================

def test_familia_onu_no_mata_cuando_el_texto_muestra_producto():
    """POLÍTICA REVISADA: el código ONU dice cómo ARCHIVÓ la compra el comprador, no qué se
    fabrica. La lavandería modular del Ejército está clasificada '9111 servicio doméstico' y los
    modulares de Recoleta '5611 muebles'. Dejar que la familia matara sola costaba dos
    licitaciones reales. Sirve para desempatar cuando el texto no dice nada, no para sentenciar."""
    lic = _con_onu("Adquisición de lavandería modular", "9111",
                   "Adquisición, instalación y puesta en marcha de una lavandería modular.")
    assert triage.gate_producto(lic, excluir=[])["pasa"] is True


def test_familia_onu_fuera_si_mata_cuando_no_hay_senal_de_producto():
    lic = _con_onu("Convenio de servicios", "7612",
                   "Manejo, tratamiento y disposición final de desechos peligrosos.")
    r = triage.gate_producto(lic, excluir=[])
    assert r["pasa"] is False and r["senal"] == "onu_fuera"


def test_core_archivado_en_familia_ajena_pasa_con_confianza_baja():
    lic = _con_onu("Contenedor de oficina", "5611", "Contenedor habilitado como oficina.")
    r = triage.gate_producto(lic, excluir=[])
    assert r["pasa"] is True and r["confianza"] == "baja"


def test_exclusion_curada_no_matchea_en_el_nombre_de_la_comuna():
    """CASO REAL: la exclusión 'puente' (pensada para obras de puente) matcheaba en «Puente Alto»
    y mataba una licitación del Hospital Sótero del Río. El topónimo entró al leer la descripción."""
    lic = _lic("ARRIENDO DE MODULOS ESTADÍSTICAS RR.HH. Y URGENCIA",
               "Arriendo de módulos en dependencias del Hospital Dr. Sótero del Río, "
               "ubicado en Av. Concha y Toro 3459, comuna de Puente Alto.",
               comuna="Puente Alto", region="Región Metropolitana de Santiago")
    assert triage.gate_producto(lic, excluir=["puente"])["pasa"] is True


def test_familia_onu_core_pasa_sin_palabra_clave():
    lic = _con_onu("Provisión e instalación de recintos prefabricados", "3020",
                   "Provisión e instalación según especificaciones.")
    r = triage.gate_producto(lic)
    assert r["pasa"] is True and r["senal"] == "onu_core"


def test_familia_onu_ausente_no_rompe():
    assert triage.gate_producto(_lic("Contenedor de oficina"))["pasa"] is True


def test_conflicto_core_mas_negativa_pasa_pero_con_confianza_baja():
    """Un contenedor de oficina que menciona refrigeración no debe morir por la palabra;
    va a revisión humana."""
    r = triage.gate_producto(_lic(
        "Contenedor oficina con equipo de refrigeración",
        "Contenedor habilitado como oficina, incluye equipo de refrigeración para la sala."))
    assert r["pasa"] is True and r["confianza"] == "baja" and r["senal"] == "conflicto"


# =========================== gate de calendario ============================

HOY = datetime(2026, 8, 9, 10, 0)


def test_visita_del_api_vencida_descarta():
    lic = _lic("Contenedor oficina", fecha_visita="2026-08-04T11:00:00")
    assert triage.gate_calendario(lic, HOY)["pasa"] is False


def test_visita_del_api_futura_pasa():
    lic = _lic("Contenedor oficina", fecha_visita="2026-08-20T11:00:00")
    assert triage.gate_calendario(lic, HOY)["pasa"] is True


def test_visita_leida_del_pliego_vencida_descarta():
    """El API trae FechaVisitaTerreno null SIEMPRE; la fecha real sale del pliego."""
    lic = _lic("Contenedor oficina", visita_caracter="obligatoria",
               visita_fecha_txt="04/08/2026 · 11:00")
    r = triage.gate_calendario(lic, HOY)
    assert r["pasa"] is False and "ya pasó" in r["motivo"]


def test_visita_del_pliego_en_formato_literal():
    lic = _lic("x", visita_caracter="obligatoria", visita_fecha_txt="12 de agosto de 2026 · 10:00")
    assert triage.gate_calendario(lic, HOY)["pasa"] is True


def test_sin_dato_de_visita_no_descarta_pero_se_marca_no_evaluable():
    """REGRESIÓN CONTRA EL DISEÑO ORIGINAL: montar el gate sólo sobre el campo del API daría un
    filtro que nunca dispara (viene null en el 100% de los casos). Hay que decir 'no sé', no
    'está bien'."""
    r = triage.gate_calendario(_lic("Contenedor oficina"), HOY)
    assert r["pasa"] is True and r["evaluable"] is False


def test_pliego_sin_visita_es_evaluable_y_pasa():
    r = triage.gate_calendario(_lic("x", visita_caracter="sin_visita"), HOY)
    assert r["pasa"] is True and r["evaluable"] is True


def test_bandera_de_desarrollo_local():
    lic = _lic("Contenedor", organismo="I MUNICIPALIDAD DE LOS VILOS", region="Región de Coquimbo")
    assert "riesgo_desarrollo_local" in triage.gate_calendario(lic, HOY)["banderas"]


def test_sin_bandera_en_region_de_las_bases():
    lic = _lic("Contenedor", organismo="I MUNICIPALIDAD DE PUERTO MONTT", region="Región de los Lagos")
    assert triage.gate_calendario(lic, HOY)["banderas"] == []


# =========================== el embudo completo ============================

def test_el_embudo_corta_en_el_primer_gate_que_falla():
    r = triage.evaluar(_lic("Desarrollo de plataforma modular", "software"), HOY)
    assert r["pasa"] is False and r["gate_fallado"] == "producto"
    assert "calendario" not in r["gates"]        # no sigue evaluando


def test_el_embudo_deja_pasar_lo_bueno_y_lista_lo_pendiente():
    r = triage.evaluar(_lic("Adquisición de contenedores para oficina",
                            "Contenedores habilitados como módulos de oficina."), HOY)
    assert r["pasa"] is True
    assert "presupuesto" in r["gates_pendientes"]     # Gate 2 aún no existe: se declara
    assert "calendario" in r["gates_pendientes"]      # sin bases todavía, no se sabe


def test_una_visita_vencida_mata_aunque_el_producto_sea_core():
    """El bug central del modelo viejo: nada compensa un filtro eliminatorio."""
    r = triage.evaluar(_lic("Adquisición de contenedores modulares para oficina",
                            "Contenedores de oficina.",
                            visita_caracter="obligatoria",
                            visita_fecha_txt="01/08/2026"), HOY)
    assert r["pasa"] is False and r["gate_fallado"] == "calendario"


# =========================== divisores de margen ===========================

def test_los_divisores_salen_de_la_cascada_de_impuestos():
    """Los viejos (1,625 / 1,885) eran markup sobre costo y sin impuestos. La definición de Loveo
    es margen NETO sobre la venta después de PPM 2%, previsión de IVA 10% y renta 25%: eso baja
    el costo base autorizado alrededor de un 28%."""
    lim, sano = triage.divisores()
    assert 2.0 < lim < 2.2, f"límite (25%) debería rondar 2,08 y dio {lim}"
    assert 2.6 < sano < 2.9, f"objetivo (35%) debería rondar 2,75 y dio {sano}"
    assert lim > 1.625, "el techo nuevo es más estricto que el viejo, no más laxo"


def test_el_techo_de_costo_es_coherente_con_el_margen_que_promete():
    """Invertir la cascada y volver a aplicarla tiene que devolver el mismo margen."""
    import costos_parametricos as cp
    techo_neto = 100_000_000
    base = cp.techo_costo(techo_neto, 0.25)
    m = cp.margenes(techo_neto, base, margen_error=0)
    assert abs(m["margen_optimista"] - 0.25) < 0.01
