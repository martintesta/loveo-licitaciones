"""
costos_parametricos.py — Costo estimado sin leer las bases. Insumo del Gate 2 del triage.

TODO ESTO SALE DE PROYECTOS GANADOS Y EJECUTADOS, no de supuestos. Fuentes (2025 - ene 2026):
  Coquimbo · Rancagua · San Felipe (camarines) · Quillón (sala REAS) · Talagante (box dental + RX)
  · Vicuña · Maipú · Chiloé-Castro · Diego de Almagro · Zapallar · Puchuncaví
y la planilla de seguimiento de flujos con costo ESTIMADO vs costo REAL de cada uno.

DOS HALLAZGOS QUE CAMBIAN EL MODELO FINANCIERO
1. El margen de Loveo se calcula SOBRE EL NETO Y DESPUÉS DE IMPUESTOS: PPM 2%, previsión de
   IVA 10% y renta 25% a provisionar (definición de Martín, ago-2026). La planilla de flujos
   muestra el margen OPERATIVO —Vicuña: (30.252.101 − 24.544.067)/30.252.101 = 18,9%— que es
   sobre venta pero antes de impuestos; el margen que decide el GO/NO-GO es el de después.
   Los divisores pasan de 1,625/1,885 (markup sobre costo, sin impuestos) a 2,081 (mínimo 25%)
   y 2,752-3,281 (objetivo 35-40%): el costo base autorizado baja ~28%.
2. El sobrecosto del 30% es EMPÍRICAMENTE CORRECTO, pero se estaba aplicando tarde. Medido sobre
   los 5 proyectos cerrados: costo_real / costo_estimado = 1,304 en promedio (σ = 0,14). O sea el
   30% no es un colchón conservador: es el valor esperado. Los proyectos que decepcionaron son
   exactamente aquellos donde el margen se prometió SIN aplicarlo.

  costo_modulo(tipo, n)      -> CLP por el módulo base y su acondicionamiento
  costo_m2(tipo)             -> CLP/m² para cuando se conoce la superficie y no el nº de módulos
  flete(km, n_modulos)       -> CLP reales, no puntos de una escala
  estimar(...)               -> los dos métodos + su divergencia (nunca uno solo en silencio)
"""
import os

# --- Verificado contra la planilla de flujos: 5 proyectos con estimado y real ---
SOBRECOSTO_MEDIDO = 0.304          # costo_real / costo_estimado − 1
SOBRECOSTO_SIGMA = 0.14            # dispersión: 1,156 (Coquimbo) a 1,515 (Maipú)
MARGEN_SOBRE = "neto_post_impuestos"   # ver la cascada más abajo
FECHA_DATOS = "2026-01"            # los precios unitarios son de esta fecha: reajustar

# --- Módulo base, por tipo. Precio unitario REAL pagado, sin acondicionar ----
# Coquimbo 2×$2.750.000 · Rancagua 2×$1.900.000 · San Felipe 2×$4.343.500 (camarines)
# Chiloé $2.000.000 · Vicuña $2.377.500
MODULO_BASE = {
    "container_20_usado":   1_700_000,   # mercado ene-2026, verificado en la web (1,6-1,7M)
    "modulo_simple":        1_900_000,   # Rancagua: oficina básica
    "modulo_estandar":      2_750_000,   # Coquimbo: el caso típico
    "modulo_camarin":       4_343_500,   # San Felipe: con sanitario y alcantarillado
    "modulo_clinico":       5_500_000,   # Talagante: box dental con terminaciones clínicas
}

# --- Acondicionamiento por módulo, promediado de los itemizados reales ------
# Coquimbo: techumbre 734k + puertas/ventanas 795k + piso 620k + terminaciones 300k +
#           eléctrica 340k = 2.789k por 2 módulos → ~1.395k/módulo
# Rancagua: eléctrico 250k + piso 300k + ángulos 100k + techumbre 350k + hojalatería 100k +
#           armado 400k = 1.500k/módulo
ACONDICIONAMIENTO = {
    "basico":     1_450_000,    # techumbre, piso, puertas/ventanas, eléctrica, terminaciones
    "sanitario":  2_500_000,    # + alcantarillado, agua potable, artefactos (San Felipe: 725k
                                #   de alcantarillado y AP sobre 2 módulos, más artefactos)
    "clinico":    6_800_000,    # Talagante: plomo en sala RX, mobiliario STARON, termopanel, AC
    "reas":       4_200_000,    # Quillón: paneles frigoríficos, inox, rampla, extractor, señalética
}

# --- Mano de obra e instalación, de los mismos itemizados -------------------
MO_POR_MODULO = 600_000         # Coquimbo 1.170k/2 · Rancagua 400k/2+armado · San Felipe 400k/2
APOYOS_HORMIGON_POR_MODULO = 300_000   # San Felipe 303k · Talagante 1.226k/10 apoyos

# --- Flete: CLP reales por viaje, medidos ----------------------------------
# Maipú 30 km → 350k · Rancagua 90 km → 410k/mód · Quillón 400 km → 500k
# Coquimbo/Vicuña 470 km → 2,0-2,35M · Diego de Almagro 900 km → 2,5M · Chiloé 1.100 km → 2,5M
FLETE_TRAMOS = [(50, 350_000), (150, 500_000), (450, 900_000),
                (700, 2_200_000), (1000, 2_500_000), (99999, 3_200_000)]


def flete(km, n_modulos=1):
    """CLP reales. NO se convierte a una escala de puntos: el flete es la partida que más varía
    entre una licitación cerca y una lejos, y pasarlo a 1-9 tira justo esa información."""
    if km is None:
        return None
    base = next(v for tope, v in FLETE_TRAMOS if km <= tope)
    # el segundo módulo del mismo viaje no cuesta otro flete completo
    return int(base * (1 + 0.6 * max(0, n_modulos - 1)))


def costo_modulo(tipo="modulo_estandar", acondicionamiento="basico", n=1, km=None):
    """Costo directo estimado por el método MÓDULO."""
    base = MODULO_BASE.get(tipo, MODULO_BASE["modulo_estandar"])
    acond = ACONDICIONAMIENTO.get(acondicionamiento, ACONDICIONAMIENTO["basico"])
    por_modulo = base + acond + MO_POR_MODULO + APOYOS_HORMIGON_POR_MODULO
    return int(por_modulo * n + (flete(km, n) or 0))


# --- CLP/m²: derivado de los mismos proyectos ------------------------------
# Un módulo estándar de container 20' útil ≈ 14,8 m². Coquimbo: 11,64M / (2×14,8) = 393k/m².
# Rancagua: 8,02M / 29,6 = 271k/m². San Felipe camarines: 11,40M / 29,6 = 385k/m².
# Talagante box dental: ~27 m² de piso (revestimiento vinílico 27 m²) con costo directo alto.
COSTO_M2 = {
    "modulo_simple":    271_000,
    "modulo_estandar":  393_000,
    "modulo_camarin":   385_000,
    "modulo_clinico":   900_000,     # terminaciones clínicas, plomo, mobiliario
    "reas":             350_000,
}
M2_POR_MODULO_20 = 14.8


def costo_m2(tipo="modulo_estandar", m2=None, km=None, n_modulos=1):
    """Costo directo estimado por el método SUPERFICIE."""
    if not m2:
        return None
    return int(COSTO_M2.get(tipo, COSTO_M2["modulo_estandar"]) * m2 + (flete(km, n_modulos) or 0))


DIVERGENCIA_MAX = float(os.environ.get("LOVEO_DIVERGENCIA_MAX", "0.15"))


def estimar(tipo="modulo_estandar", acondicionamiento="basico", n_modulos=1, m2=None, km=None):
    """Los DOS métodos y su divergencia. Nunca elige uno en silencio.

    Cuando m² y nº de módulos no cuentan la misma historia, el dato de entrada está mal estimado
    y quien revisa tiene que verlo — por eso se devuelve el flag en vez de promediar y seguir."""
    a = costo_modulo(tipo, acondicionamiento, n_modulos, km)
    b = costo_m2(tipo, m2 or (n_modulos * M2_POR_MODULO_20), km, n_modulos)
    div = abs(a - b) / max(a, b) if (a and b) else None
    inconsistente = bool(div is not None and div > DIVERGENCIA_MAX)
    base = min(a, b) if inconsistente else int(((a or 0) + (b or a)) / 2)   # el conservador manda
    return {
        "costo_base": base,
        "metodo_modulo": a, "metodo_m2": b,
        "divergencia": round(div, 3) if div is not None else None,
        "costo_base_inconsistente": inconsistente,
        "flete": flete(km, n_modulos),
        "fecha_datos": FECHA_DATOS,
    }


# ---------------------------------------------------------------------------
# Cascada de impuestos — definición de Martín (ago-2026)
# ---------------------------------------------------------------------------
# "El margen se calcula sobre el Neto y descontando los impuestos a pagar por ese proyecto: el
#  PPM 2% por proyecto, el IVA, y el impuesto a la ganancia a previsionar para el año siguiente."
#
# Los parámetros salen de las planillas de Loveo, no de la teoría:
#   · Zapallar: "Previsión de IVA (10%)" = 1.373.659 sobre ingresos de 13.736.590. Es exactamente
#     el 10%, y es la regla que Loveo aplica. El 19% nominal no se paga entero porque los
#     materiales traen crédito fiscal; el 10% es el neto efectivo medido.
#   · Zapallar: "Impuestos SII 1.070.885 — ppm + iva" confirma que ambos se tratan como salida
#     del proyecto.
#
# NOTA CONTABLE, deliberadamente no aplicada: el PPM es un ANTICIPO que se acredita contra el
# impuesto a la renta anual, así que restar los dos por separado sobrecuenta ~2% del neto. Se
# deja así porque es la provisión que Martín pidió y peca de conservadora, que en un filtro de
# GO/NO-GO es el lado correcto para equivocarse. `PPM_ACREDITA_RENTA=True` da la versión contable.
PPM = float(os.environ.get("LOVEO_PPM", "0.02"))
PREVISION_IVA = float(os.environ.get("LOVEO_PREVISION_IVA", "0.10"))
IMPUESTO_RENTA = float(os.environ.get("LOVEO_RENTA", "0.25"))
PPM_ACREDITA_RENTA = os.environ.get("LOVEO_PPM_ACREDITA", "0") == "1"

# Los precios unitarios de las planillas son BRUTOS (con IVA): Quillón lo deja explícito —
# "Total materiales 4.163.000 / Neto materiales 3.498.319" = 4.163.000/1,19. Para comparar contra
# un techo NETO hay que convertirlos, o el costo queda inflado un 19%.
COSTO_ES_BRUTO = True
FRACCION_COSTO_CON_IVA = 0.80      # Quillón 81%, San Felipe 93%; la mano de obra no lleva crédito


def costo_a_neto(costo_bruto, fraccion=None):
    """Los precios paramétricos vienen con IVA. El techo de la licitación es neto."""
    if not COSTO_ES_BRUTO:
        return costo_bruto
    f = FRACCION_COSTO_CON_IVA if fraccion is None else fraccion
    return costo_bruto * f / 1.19 + costo_bruto * (1 - f)


def margenes(monto_neto, costo_base, margen_error=None, detalle=False, costo_ya_neto=False):
    """Margen NETO DESPUÉS DE IMPUESTOS sobre el precio de oferta, como lo define Loveo.

    Cascada: precio neto − costo (a neto, con sobrecosto) − PPM − previsión IVA − renta."""
    if not monto_neto:
        return None
    err = SOBRECOSTO_SIGMA if margen_error is None else margen_error
    f = 1 + SOBRECOSTO_MEDIDO

    def cascada(costo_bruto_con_sobrecosto):
        # `costo_ya_neto` importa: las cubicaciones de los análisis están en neto, los precios
        # de las planillas de compra están en bruto. Convertir dos veces descuenta un 19% que
        # no existe y hace pasar licitaciones que no cierran.
        costo = (costo_bruto_con_sobrecosto if costo_ya_neto
                 else costo_a_neto(costo_bruto_con_sobrecosto))
        bruto = monto_neto - costo
        ppm = PPM * monto_neto
        iva = PREVISION_IVA * monto_neto
        base = max(0.0, bruto - iva - (0.0 if PPM_ACREDITA_RENTA else ppm))
        renta = IMPUESTO_RENTA * base
        if PPM_ACREDITA_RENTA:
            renta = max(0.0, renta - ppm)          # el PPM se acredita, no se suma
        final = bruto - ppm - iva - renta
        return final / monto_neto, {"costo_neto": round(costo), "utilidad_operativa": round(bruto),
                                    "ppm": round(ppm), "iva": round(iva), "renta": round(renta),
                                    "utilidad_final": round(final)}

    opt, d_opt = cascada(costo_base * f)
    cons, d_cons = cascada(costo_base * (1 + err) * f)
    r = {"margen_optimista": round(opt, 4), "margen_conservador": round(cons, 4),
         "semaforo": "verde" if cons > 0.30 else "rojo" if cons < 0.12 else "amarillo",
         "descarta": opt < 0}
    if detalle:
        r["cascada_optimista"], r["cascada_conservadora"] = d_opt, d_cons
    return r


def techo_costo(monto_neto, margen_objetivo):
    """Costo base BRUTO máximo para alcanzar ese margen neto. Invierte la cascada.

    Reemplaza a los divisores 1,625/1,885 (markup sobre costo, sin impuestos), que autorizaban
    costos muy por encima de lo que la política de margen realmente permite."""
    t = 1.0 - PPM - PREVISION_IVA
    # margen = (1 − c/P − PPM − IVA) − renta ; renta = R × (1 − c/P − IVA [− PPM])
    base_sin_ppm = t if not PPM_ACREDITA_RENTA else (1.0 - PREVISION_IVA)
    c_sobre_p = base_sin_ppm - (margen_objetivo + (PPM if PPM_ACREDITA_RENTA else 0.0)) / (1 - IMPUESTO_RENTA)
    if c_sobre_p <= 0:
        return 0
    costo_neto_max = c_sobre_p * monto_neto
    bruto = costo_neto_max / (FRACCION_COSTO_CON_IVA / 1.19 + (1 - FRACCION_COSTO_CON_IVA))
    return int(bruto / (1 + SOBRECOSTO_MEDIDO))
