"""
test_excel_analisis.py — Sensor del generador de Excel.

El test que importa es `test_editar_la_cantidad_recalcula_toda_la_cadena`: NO mira que las celdas
"parezcan fórmulas", las EJECUTA con un motor de planillas real y verifica que el número cambie.
Es la única forma honesta de sostener la promesa "editás Cantidad y todo recalcula" — openpyxl
escribe fórmulas pero no las evalúa, así que un `=A1*B1` mal referenciado pasa cualquier test de
strings y falla recién cuando Martín abre el archivo.

Requiere el paquete `formulas` (pip install formulas). Si no está, ese test se salta (el resto no).

  python -m pytest tests/test_excel_analisis.py -q
"""
import os
import tempfile

import pytest

import analisis
import excel_analisis

CANT, PRECIO_UNIT, FLETE = 2, 3_051_000, 700_000     # el container real del catálogo de Loveo


def _datos(cantidad=CANT, techo=40_000_000, **kw):
    D = {
        "meta": {"id": "T-1", "nombre": "Test", "organismo": "O", "comuna": "C", "region": "Maule",
                 "fecha_publicacion": "2026-08-01", "fecha_cierre": "2026-08-20",
                 "dias_restantes": 12, "fecha_analisis": "2026-08-08",
                 "base_operativa": "Pirque", "distancia_km_base": 250},
        "presupuesto": {"monto_disponible": techo, "neto_o_iva": "neto", "notas": ""},
        "params": dict(analisis.PARAMS),
        "cubicacion": [
            {"partida": "Container oficina modular", "unidad": "un", "cantidad": cantidad,
             "precio_unitario": PRECIO_UNIT, "notas": ""},
            {"partida": "Flete", "unidad": "un", "cantidad": 1, "precio_unitario": FLETE, "notas": ""}],
        "capital_adelantado": None,
        "scoring": {"margen": 7, "cashflow": 5, "complejidad": 6, "logistico": 7,
                    "alineacion": 9, "repetibilidad": 8},
        "raci": [], "plazos": [], "compras": [], "riesgos": [],
        "objeto_alineacion": {"objeto": "x", "familia": "modular", "alineacion_score": 9,
                              "alineacion_comentario": "", "referencia_competitiva": ""},
        "estrategia": {"texto": "t", "precio_recomendado_pct": 0.95},
        "info_faltante": [],
    }
    D.update(kw)
    return D


def _etiquetas(ws):
    """{etiqueta de la columna A: valor de la columna B}"""
    return {str(r[0].value).strip(): r[1].value for r in ws.iter_rows()
            if r[0].value and len(r) > 1}


# ------------------------------------------------------------------ el sensor de verdad
def test_editar_la_cantidad_recalcula_toda_la_cadena():
    """Duplicar la Cantidad en «Cubicación» tiene que duplicar el costo base y arrastrar sobrecosto,
    financiamiento y precio objetivo — y hacerlo CRUZANDO de hoja hasta los KPIs del Resumen."""
    formulas = pytest.importorskip("formulas", reason="pip install formulas para el sensor de fórmulas")

    def recalcular(cantidad):
        wb = excel_analisis.construir(_datos(cantidad))
        ruta = os.path.join(tempfile.mkdtemp(), "t.xlsx")
        wb.save(ruta)
        # direcciones por ETIQUETA, no por número de fila: si el layout se mueve, el test sigue vivo
        refs = {}
        for hoja in ("Financiero", "Resumen"):
            for fila in wb[hoja].iter_rows():
                if isinstance(fila[0].value, str) and len(fila) > 1:
                    refs[(hoja, fila[0].value.strip())] = (hoja, fila[0].row)
        sol = formulas.ExcelModel().loads(ruta).finish().calculate()
        valores = {}
        for (hoja, etiqueta), (h, fila) in refs.items():
            sufijo = f"]{h}'!B{fila}".upper()
            for clave, celda in sol.items():
                if clave.upper().endswith(sufijo):
                    try:
                        valores[(hoja, etiqueta)] = celda.value[0, 0]
                    except (AttributeError, TypeError, IndexError):
                        pass
                    break
        return valores

    P = analisis.PARAMS
    v1, v2 = recalcular(CANT), recalcular(CANT * 2)
    base1 = CANT * PRECIO_UNIT + FLETE
    base2 = CANT * 2 * PRECIO_UNIT + FLETE
    assert base2 != base1

    esperado = [
        ("Financiero", "Costo base directo", base1, base2),
        ("Financiero", "+ sobrecosto", base1 * (1 + P["sobrecosto"]), base2 * (1 + P["sobrecosto"])),
        ("Financiero", "Costo financiamiento (tasa × capital)",
         base1 * (1 + P["sobrecosto"]) * P["tasa_financiamiento"],
         base2 * (1 + P["sobrecosto"]) * P["tasa_financiamiento"]),
        ("Financiero", "Precio objetivo",
         base1 * (1 + P["sobrecosto"]) * P["markup_obj"],
         base2 * (1 + P["sobrecosto"]) * P["markup_obj"]),
        ("Resumen", "Costo base directo (suma de la Cubicación)", base1, base2),
        ("Resumen", "Costo con sobrecosto", base1 * (1 + P["sobrecosto"]), base2 * (1 + P["sobrecosto"])),
    ]
    for hoja, etiqueta, e1, e2 in esperado:
        assert (hoja, etiqueta) in v1, f"no se pudo evaluar {hoja}!{etiqueta}"
        assert v1[(hoja, etiqueta)] == pytest.approx(e1, rel=1e-6), f"{hoja}!{etiqueta} con cantidad {CANT}"
        assert v2[(hoja, etiqueta)] == pytest.approx(e2, rel=1e-6), f"{hoja}!{etiqueta} con cantidad {CANT * 2}"


def test_los_techos_de_costo_del_excel_son_los_del_modelo():
    """cb_max_obj = techo/1,885 y cb_max_min = techo/1,625 — los mismos factores del consolidado."""
    formulas = pytest.importorskip("formulas", reason="pip install formulas para el sensor de fórmulas")
    techo = 40_000_000
    wb = excel_analisis.construir(_datos(techo=techo))
    ruta = os.path.join(tempfile.mkdtemp(), "t.xlsx")
    wb.save(ruta)
    filas = {str(r[0].value).strip(): r[0].row for r in wb["Financiero"].iter_rows() if r[0].value}
    sol = formulas.ExcelModel().loads(ruta).finish().calculate()

    def leer(etiqueta):
        sufijo = f"]FINANCIERO'!B{filas[etiqueta]}".upper()
        for clave, celda in sol.items():
            if clave.upper().endswith(sufijo):
                return celda.value[0, 0]
        return None

    assert leer("Costo base MÁX p/ margen objetivo") == pytest.approx(techo / analisis.FACTOR_SANO)
    assert leer("Costo base MÁX p/ margen mínimo") == pytest.approx(techo / analisis.FACTOR_LIMITE)


# ------------------------------------------------------------------ estructura y bordes
def test_python_y_excel_calculan_lo_mismo():
    """Los semáforos se calculan en Python y las celdas en Excel: los dos caminos tienen que coincidir,
    si no el Resumen dice 'Sano' arriba y muestra un margen de riesgo abajo."""
    D = _datos()
    fin = excel_analisis._finanzas(D)
    assert fin["costo_base"] == CANT * PRECIO_UNIT + FLETE
    assert fin["costo_ss"] == pytest.approx(fin["costo_base"] * (1 + analisis.PARAMS["sobrecosto"]))
    assert fin["cb_max_obj"] == pytest.approx(fin["techo"] / analisis.FACTOR_SANO)
    m = excel_analisis._margenes(fin, fin["techo"] * 0.95)
    assert m["un"] == pytest.approx((m["ub"] - m["ppm"]) * (1 - analisis.PARAMS["impuesto_renta"]))


def test_sin_matriz_de_evaluacion_no_hay_hoja_de_estrategia():
    wb = excel_analisis.construir(_datos())
    assert "Estrategia Ganar" not in wb.sheetnames


def test_censo_sin_probabilidades_no_se_usa_para_simular():
    """Bug sutil: con competidores pero sin p_eett, θ=0 → 'nadie califica' → 'Loveo gana siempre'.
    Esa conclusión es falsa y peligrosa; el censo solo alimenta la simulación si trae probabilidades."""
    ev = {"criterios": [
        {"nombre": "Precio", "peso": 40, "tipo": "continuo", "escalones": []},
        {"nombre": "EETT", "peso": 60, "tipo": "binario", "es_compuerta": True,
         "escalones": [{"pts": 60, "cond": "Cumple", "p_rival": 0.5},
                       {"pts": 0, "cond": "No", "p_rival": 0.5}]}],
        "no_evaluado": [], "reglas_estructurales": [],
        "supuestos_competencia": {"n_competidores": [2, 4], "precio_rival_pct": [0.8, 1.0]},
        "plan_accion": []}
    sin_prob = {"empresas": [{"nombre": "Rival", "amenaza": "ALTA"}]}
    D = _datos(evaluacion=ev, competencia=sin_prob)
    E = excel_analisis._estrategia(D, excel_analisis._finanzas(D))
    assert E and E["usa_censo"] is False
    assert all(m["pw"] < 1.0 for m in E["mc"]), "sin θ no puede concluir que gana siempre"

    con_prob = {"empresas": [{"nombre": "Rival", "amenaza": "ALTA", "p_eett": 0.6, "p_plazo": 0.5,
                              "p_gar": 0.7, "p_integ": 0.6, "p_form": 0.85}]}
    D2 = _datos(evaluacion=ev, competencia=con_prob)
    E2 = excel_analisis._estrategia(D2, excel_analisis._finanzas(D2))
    assert E2["usa_censo"] is True and E2["theta_prom"] > 0


def test_la_simulacion_es_reproducible():
    """Semilla fija: dos corridas del mismo input dan el mismo precio robusto. Si no, el Excel de
    hoy y el de mañana recomiendan precios distintos sin que cambie nada."""
    ev = {"criterios": [
        {"nombre": "Precio", "peso": 40, "tipo": "continuo", "escalones": []},
        {"nombre": "EETT", "peso": 60, "tipo": "binario",
         "escalones": [{"pts": 60, "cond": "Cumple", "p_rival": 0.5},
                       {"pts": 0, "cond": "No", "p_rival": 0.5}]}],
        "no_evaluado": [], "reglas_estructurales": [],
        "supuestos_competencia": {"n_competidores": [2, 4], "precio_rival_pct": [0.8, 1.0],
                                  "n_simulaciones": 2000},
        "plan_accion": []}
    D = _datos(evaluacion=ev)
    fin = excel_analisis._finanzas(D)
    a = excel_analisis._estrategia(D, fin)
    b = excel_analisis._estrategia(D, fin)
    assert a["p_robusto"] == b["p_robusto"]
    assert [m["pw"] for m in a["mc"]] == [m["pw"] for m in b["mc"]]


def test_escalones_sin_probabilidad_se_normalizan():
    esc = excel_analisis._escalones({"peso": 10, "escalones": [{"pts": 10, "cond": "a", "p_rival": 2},
                                                              {"pts": 0, "cond": "b", "p_rival": 2}]})
    assert sum(e["p_rival"] for e in esc) == pytest.approx(1.0)
    esc0 = excel_analisis._escalones({"peso": 10, "escalones": [{"pts": 10, "cond": "a", "p_rival": 0},
                                                               {"pts": 0, "cond": "b", "p_rival": 0}]})
    assert sum(e["p_rival"] for e in esc0) == pytest.approx(1.0)
