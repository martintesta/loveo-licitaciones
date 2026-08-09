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
from datetime import datetime

import costos_parametricos as cp
import db
import schema_v3

# Umbrales del veredicto, sobre el margen NETO después de impuestos.
GO = float(os.environ.get("LOVEO_UMBRAL_GO", "0.35"))
LIMITE = float(os.environ.get("LOVEO_UMBRAL_LIMITE", "0.25"))
AJUSTADO = float(os.environ.get("LOVEO_UMBRAL_AJUSTADO", "0.12"))

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


def _costo_de_cubicacion(codigo):
    """Suma la cubicación del análisis si existe. Está en NETO."""
    p = os.path.join(DIR_ANALISIS, f"{codigo}.json")
    if not os.path.isfile(p):
        return None
    try:
        d = json.load(open(p, encoding="utf-8"))
    except (ValueError, OSError):
        return None
    total = sum((x.get("cantidad") or 0) * (x.get("precio_unitario") or 0)
                for x in (d.get("cubicacion") or []))
    return total or None


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

    # El monto de la BD es el publicado (con IVA); el margen se calcula sobre el NETO.
    neto = monto / 1.19
    base = _costo_de_cubicacion(cod)
    if base:
        m = cp.margenes(neto, base, costo_ya_neto=True, detalle=True)
        fuente = "cubicacion"
    else:
        return {"margen_neto": None, "veredicto": None, "costo_base": None, "fuente": None,
                "motivo": "sin cubicación: falta analizar o estimar los módulos"}
    return {"margen_neto": m["margen_conservador"], "veredicto": etiqueta(m["margen_conservador"]),
            "costo_base": base, "fuente": fuente, "neto": round(neto),
            "cascada": m.get("cascada_conservadora"),
            "motivo": f"margen neto {m['margen_conservador']:.1%} sobre techo neto de "
                      f"${round(neto):,}".replace(",", ".")}


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
            "       margen_neto, veredicto_fin, costo_base_est, estado_revision, visita_caracter "
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
        neto = (f["monto_estimado"] or 0) / 1.19
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
