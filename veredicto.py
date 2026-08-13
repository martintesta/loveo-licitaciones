"""
veredicto.py — El GO/NO-GO financiero vive en la licitación, no en un Excel suelto.

Hasta ahora el veredicto se calculaba dentro del análisis y quedaba escrito en un .xlsx dentro de
la carpeta de la licitación. Eso tiene dos problemas: hay que abrir el archivo para saberlo, y
cuando la política de margen cambia (pasó: se activó la cascada de impuestos y el techo de costo
bajó 28%) los Excel viejos siguen diciendo lo de antes. Acá se recalcula desde el dato y se
guarda en la licitación, así el tablero lo muestra sin abrir nada.

  calcular(codigo)      -> {margen_neto, veredicto, costo_base, fuente} sin escribir
  guardar(codigo)       -> lo calcula y lo persiste en licitaciones.veredicto_*
  recalcular_todos()    -> reaplica la política vigente a toda la base
  prioridad(limite)     -> lo que sigue vivo, ordenado por cierre

  python veredicto.py --recalcular
  python veredicto.py --prioridad
"""
import json
import os
import re
from datetime import datetime

import costos_parametricos as cp
import db
import schema_v3

# --------------------------------------------------------------------------------------------
# EL VEREDICTO SE MIDE POR DÍA-CUADRILLA, NO POR MARGEN PORCENTUAL
# --------------------------------------------------------------------------------------------
# Los umbrales viejos (GO 35% · LIMITE 25% · AJUSTADO 12% sobre margen neto) tenían dos defectos.
#
# 1. UNIDAD EQUIVOCADA. La política "margen 25% mínimo, 35-40% objetivo" siempre fue margen bruto
#    sobre el precio; se aplicaba como margen NETO después de PPM, IVA y renta. Como
#    neto = 0,75 × operativo − 9,5 puntos, un GO de 35% neto exigía 59,3% de margen operativo.
#    El récord histórico de Loveo es 18,9% (Vicuña). Ninguno de los cinco proyectos ejecutados
#    calificaba siquiera como AJUSTADO: el listón describía una empresa que no existe.
#
# 2. FORMA EQUIVOCADA. Un porcentaje no paga sueldos. Con una sola cuadrilla de 3 personas y
#    ~250 días-cuadrilla al año, lo escaso no es el margen: son los días. Talagante lo probó —
#    +$12.000.000 de contribución, más que ningún otro proyecto del año, y el peor negocio:
#    120 días-cuadrilla a $100.000/día contra un piso de $192.000. Déficit $11.040.000.
#
# El piso NO se elige: sale de la estructura fija ($4.000.000/mes) dividida por la capacidad
# anual. Las bandas salen del error medido de la estimación de costo (σ = 0,14).
# Ver costos_parametricos.veredicto_capacidad.
UMBRAL_LEGACY_GO = float(os.environ.get("LOVEO_UMBRAL_GO", "0.35"))
UMBRAL_LEGACY_LIMITE = float(os.environ.get("LOVEO_UMBRAL_LIMITE", "0.25"))
UMBRAL_LEGACY_AJUSTADO = float(os.environ.get("LOVEO_UMBRAL_AJUSTADO", "0.12"))
# Retrocompatibilidad: `etiqueta()` sigue existiendo para el margen porcentual.
GO, LIMITE, AJUSTADO = UMBRAL_LEGACY_GO, UMBRAL_LEGACY_LIMITE, UMBRAL_LEGACY_AJUSTADO

# Las cubicaciones de los análisis viven acá; son mejores que el paramétrico cuando existen.
DIR_ANALISIS = os.environ.get(
    "LOVEO_DIR_ANALISIS",
    r"C:\Users\marti\AppData\Local\Temp\claude\C--Users-marti-OneDrive-Escritorio-gstack"
    r"\b718b5c2-d9ea-4765-88b6-6f275690bb74\scratchpad\lote27\json")


def etiqueta(margen):
    if margen is None:
        return None
    return ("GO" if margen >= GO else "LIMITE" if margen >= LIMITE
            else "AJUSTADO" if margen >= AJUSTADO else "NO-GO")


_RX_FLETE = re.compile(r"flete|traslado|transporte", re.I)
_RX_PUERTO_MONTT = re.compile(r"puerto\s*montt", re.I)


def _costo_de_cubicacion(codigo, region=None):
    """Suma la cubicación del análisis si existe. Está en NETO.

    Corrige el ORIGEN DEL FLETE. Instrucción de Martín (ago-2026): el traslado se mide siempre
    desde Pirque. Quince de las dieciocho cubicaciones se armaron antes de esa instrucción y
    cotizan desde Puerto Montt, que para casi todo destino está mucho más lejos — el flete es la
    partida que más varía con la distancia, así que el error no es menor: en Cabildo movió el
    veredicto 50 puntos de margen.

    Se reescala la partida existente por la razón de fletes (Pirque / Puerto Montt) en vez de
    recalcularla de cero: así se respeta lo que el cubicador supuso sobre número de módulos y
    modo de transporte —el cabotaje marítimo a Magallanes no escala como un camión— y sólo se
    corrige el origen, que es lo que estaba mal."""
    p = os.path.join(DIR_ANALISIS, f"{codigo}.json")
    if not os.path.isfile(p):
        return None, []
    try:
        d = json.load(open(p, encoding="utf-8"))
    except (ValueError, OSError):
        return None, []

    razon, km_p, km_pm = None, None, None
    if region:
        try:
            import scoring
            km_p, _ = scoring._dist_min(region, "Pirque")
            km_pm, _ = scoring._dist_min(region, "Puerto Montt")
            if km_p and km_pm:
                f_p, f_pm = cp.flete(km_p), cp.flete(km_pm)
                razon = (f_p / f_pm) if (f_p and f_pm) else None
        except Exception:
            razon = None

    total, ajustes = 0.0, []
    for x in (d.get("cubicacion") or []):
        sub = (x.get("cantidad") or 0) * (x.get("precio_unitario") or 0)
        nom = x.get("partida") or ""
        if razon and razon != 1 and _RX_FLETE.search(nom) and _RX_PUERTO_MONTT.search(nom):
            nuevo = sub * razon
            ajustes.append({"partida": nom[:70], "antes": round(sub), "despues": round(nuevo),
                            "km_pirque": km_p, "km_puerto_montt": km_pm})
            sub = nuevo
        total += sub
    return (total or None), ajustes


def calcular(lic):
    """Margen neto y veredicto para una licitación (dict o Row). No escribe.

    Prefiere la cubicación real del análisis; si no hay, no inventa un costo paramétrico sin
    saber cuántos módulos son — devuelve fuente=None y veredicto None, que es honesto."""
    lic = dict(lic)
    cod = lic.get("codigo")
    monto = lic.get("monto_estimado")
    if not monto:
        return {"margen_neto": None, "veredicto": None, "costo_base": None,
                "fuente": None, "motivo": "sin monto: no se puede evaluar el techo"}

    # ¿El monto es bruto o neto? NO es constante y asumirlo cuesta caro: para 3621-41 (Cabildo)
    # el API publicó $20.501.280 y el pliego dice "$24.396.524 impuesto incluido" — el API traía
    # el NETO. Dividir igual por 1,19 bajaba el techo un 19% y volvía NO-GO algo que no lo era.
    con_iva = lic.get("monto_iva_incluido")
    if con_iva is None:
        neto, iva_conocido = monto / 1.19, False        # supuesto conservador, pero declarado
    else:
        neto, iva_conocido = (monto / 1.19 if con_iva else monto), True
    base, ajustes_flete = _costo_de_cubicacion(cod, lic.get("region"))
    if not base:
        return {"margen_neto": None, "veredicto": None, "costo_base": None, "fuente": None,
                "motivo": "sin cubicación: falta analizar o estimar los módulos"}

    m = cp.margenes(neto, base, costo_ya_neto=True, detalle=True)
    dias, senales = _dias_estimados(lic)
    v = cp.veredicto_capacidad(neto, base, dias, costo_ya_neto=True)
    if v is None:
        return {"margen_neto": m["margen_conservador"], "veredicto": None, "costo_base": base,
                "fuente": "cubicacion", "motivo": "no se pudo estimar días-cuadrilla"}

    sospechoso, motivo_sospecha = cp.demasiado_bueno(neto, base, costo_ya_neto=True)
    piso = f"${v['piso_dia']:,}".replace(",", ".")
    pordia = f"${v['por_dia']:,}".replace(",", ".")
    extra = (f" · señales de ocupación: {', '.join(senales)}" if senales else "")
    return {"margen_neto": m["margen_conservador"], "veredicto": v["veredicto"],
            "costo_base": base, "fuente": "cubicacion", "neto": round(neto),
            "iva_conocido": iva_conocido, "cascada": m.get("cascada_conservadora"),
            "dias_cuadrilla": dias, "por_dia": v["por_dia"],
            "por_dia_conservador": v["por_dia_conservador"], "piso_dia": v["piso_dia"],
            "contribucion": v["contribucion"], "sobre_el_piso": v["sobre_el_piso"],
            "senales": senales, "ajustes_flete": ajustes_flete,
            "sospechoso": sospechoso, "motivo_sospecha": motivo_sospecha,
            "motivo": f"{pordia} por día-cuadrilla contra un piso de {piso} "
                      f"({dias} días estimados){extra}"
                      + (f" · ⚠ {motivo_sospecha}" if sospechoso else "")}


# Tipo de módulo por palabra clave del objeto: define los días base. Sin señal reconocible se usa
# el estándar, que es el caso típico (Coquimbo) y el más frecuente en la base.
_TIPO_POR_TOKEN = [
    ("modulo_clinico", ("dental", "clinic", "odontolog", "rayos x", "rx", "medic")),
    ("reas", ("reas", "respel", "suspel", "residuo")),
    ("modulo_camarin", ("camarin", "camarín", "bano", "baño", "sanitario", "vestidor")),
    ("modulo_simple", ("oficina", "bodega", "garita", "paradero")),
]


def _dias_estimados(lic):
    """(días-cuadrilla, señales). Estima la OCUPACIÓN, que es lo escaso, a partir del texto.

    Es una estimación de titular y descripción, no del pliego: sirve para ordenar y para alertar.
    Cuando hay bases analizadas, la cubicación manda sobre esto."""
    import triage
    senales, _ = triage.senales_ocupacion(lic)
    texto = f"{lic.get('nombre') or ''} {lic.get('descripcion') or ''}".lower()
    tipo = next((t for t, toks in _TIPO_POR_TOKEN if any(k in texto for k in toks)),
                "modulo_estandar")
    return cp.dias_cuadrilla(tipo, 1, senales), senales


def guardar(codigo, lic=None):
    schema_v3.migrate()
    if lic is None:
        with db.conn() as c:
            r = c.execute("SELECT * FROM licitaciones WHERE codigo=?", (codigo,)).fetchone()
        if not r:
            return None
        lic = dict(r)
    v = calcular(lic)
    if v["veredicto"] is None:
        return v
    with db.conn() as c:
        c.execute("UPDATE licitaciones SET costo_base_est=?, margen_neto=?, veredicto_fin=?, "
                  "veredicto_fuente=?, veredicto_at=? WHERE codigo=?",
                  (v["costo_base"], v["margen_neto"], v["veredicto"], v["fuente"],
                   db._now(), codigo))
        db.log_evento(c, codigo, "veredicto",
                      f"{v['veredicto']} — {v['motivo']} (política vigente: PPM {cp.PPM:.0%} + "
                      f"IVA {cp.PREVISION_IVA:.0%} + renta {cp.IMPUESTO_RENTA:.0%}, "
                      f"sobrecosto {cp.SOBRECOSTO_MEDIDO:.1%})")
    return v


def recalcular_todos():
    """Reaplica la política vigente a toda la base. Se corre cuando cambia un parámetro del
    modelo financiero: los Excel viejos quedan desactualizados, la BD no."""
    schema_v3.migrate()
    with db.conn() as c:
        filas = [dict(r) for r in c.execute("SELECT * FROM licitaciones")]
    out = {"evaluadas": 0, "sin_datos": 0, "por_veredicto": {}}
    for lic in filas:
        v = guardar(lic["codigo"], lic)
        if not v or v["veredicto"] is None:
            out["sin_datos"] += 1
            continue
        out["evaluadas"] += 1
        out["por_veredicto"][v["veredicto"]] = out["por_veredicto"].get(v["veredicto"], 0) + 1
    return out


def prioridad(limite=20, hoy=None):
    """Lo que sigue vivo y da margen, ordenado por lo que cierra antes.

    El orden es por VENCIMIENTO, no por margen: un 27% que cierra en 17 días se puede trabajar;
    un 30% que cierra mañana ya no. La urgencia es la restricción que no se puede comprar."""
    hoy = hoy or datetime.now()
    schema_v3.migrate()
    out = []
    with db.conn() as c:
        filas = c.execute(
            "SELECT codigo, nombre, organismo, comuna, monto_estimado, fecha_cierre, "
            "       margen_neto, veredicto_fin, costo_base_est, estado_revision, visita_caracter, "
            "       monto_iva_incluido "
            "FROM licitaciones WHERE vigente_oferta=1 "
            "  AND estado_revision NOT IN ('descartada') "
            "  AND veredicto_fin IN ('GO','LIMITE','AJUSTADO')").fetchall()
    for f in filas:
        try:
            fc = datetime.fromisoformat(str(f["fecha_cierre"])[:19])
        except (ValueError, TypeError):
            continue
        d = (fc.date() - hoy.date()).days
        if d < 0:
            continue
        neto = ((f["monto_estimado"] or 0) / 1.19
                if f["monto_iva_incluido"] in (None, 1) else (f["monto_estimado"] or 0))
        out.append({"codigo": f["codigo"], "nombre": f["nombre"], "organismo": f["organismo"],
                    "comuna": f["comuna"], "dias": d, "cierre": fc.strftime("%d-%m-%Y %H:%M"),
                    "monto": f["monto_estimado"], "neto": round(neto),
                    "margen": f["margen_neto"], "veredicto": f["veredicto_fin"],
                    "costo_base": f["costo_base_est"],
                    "utilidad": round(neto * (f["margen_neto"] or 0)),
                    "visita": f["visita_caracter"]})
    out.sort(key=lambda x: (x["dias"], -(x["margen"] or 0)))
    return out[:limite]


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if args and args[0] == "--recalcular":
        print(json.dumps(recalcular_todos(), indent=2, ensure_ascii=False))
    elif args and args[0] == "--prioridad":
        print(json.dumps(prioridad(), indent=2, ensure_ascii=False, default=str))
    elif args:
        print(json.dumps(guardar(args[0]), indent=2, ensure_ascii=False, default=str))
    else:
        print(__doc__)
