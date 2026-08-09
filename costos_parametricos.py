"""
costos_parametricos.py — Costo estimado sin leer las bases. Insumo del Gate 2 del triage.

TODO ESTO SALE DE PROYECTOS GANADOS Y EJECUTADOS, no de supuestos. Fuentes (2025 - ene 2026):
  Coquimbo · Rancagua · San Felipe (camarines) · Quillón (sala REAS) · Talagante (box dental + RX)
  · Vicuña · Maipú · Chiloé-Castro · Diego de Almagro · Zapallar · Puchuncaví
y la planilla de seguimiento de flujos con costo ESTIMADO vs costo REAL de cada uno.

DOS HALLAZGOS QUE CAMBIAN EL MODELO FINANCIERO
1. El margen de Loveo se calcula SOBRE LA VENTA, no sobre el costo. Verificado en la planilla
   propia: Vicuña, ingreso 30.252.101, costo real 24.544.067, "Margen Real %" 0,1887 =
   (30.252.101 − 24.544.067) / 30.252.101. Es margen sobre ingreso. Por lo tanto los divisores
   correctos son 1,733 (mínimo 25%) y 2,000-2,167 (objetivo 35-40%), no 1,625/1,885.
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
MARGEN_SOBRE = "venta"             # confirmado con la fórmula de la propia planilla
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


def margenes(monto_neto, costo_base, margen_error=None):
    """Margen optimista y conservador SOBRE LA VENTA, que es como los calcula Loveo.

    El buffer por defecto es la σ medida del sobrecosto (14%), no un 10% inventado: es la
    dispersión real entre lo que se estimó y lo que costó en los 5 proyectos cerrados."""
    if not monto_neto:
        return None
    err = SOBRECOSTO_SIGMA if margen_error is None else margen_error
    f = 1 + SOBRECOSTO_MEDIDO
    opt = (monto_neto - costo_base * f) / monto_neto
    cons = (monto_neto - costo_base * (1 + err) * f) / monto_neto
    return {"margen_optimista": round(opt, 4), "margen_conservador": round(cons, 4),
            "semaforo": "verde" if cons > 0.30 else "rojo" if cons < 0.12 else "amarillo",
            "descarta": cons < 0 and opt < 0}
