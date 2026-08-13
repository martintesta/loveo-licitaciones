"""
visitas.py — Visita a terreno: detectarla al DESCUBRIR, no al analizar.

Por qué existe este módulo. El API de Mercado Público expone `Fechas.FechaVisitaTerreno`,
y `alertas.py` lo usa para avisar. Pero el campo viene **null en el 100% de las licitaciones
medidas** (40/40 vigentes con detalle): la alerta nunca se disparó ni una vez. La visita sí
está, escrita en el pliego. En agosto de 2026 eso costó cinco licitaciones en un solo lote,
una de ellas la única financieramente sana de las dieciséis analizadas.

La detección por texto ya existía en `bases.visita_a_terreno()`, pero corría dentro de la
Capa C — o sea, recién cuando alguien decidía analizar la licitación. Para entonces la visita
suele haber pasado: se hacen a los pocos días de publicada. Este módulo la mueve al momento
en que el dato aparece por primera vez (la ingesta de las bases) y agrega la única alerta que
sirve cuando ni siquiera hay bases: **publicada hace días y todavía sin descargar**.

  detectar_y_guardar(codigo)  -> {caracter, urgencia, fecha_txt, fragmento, docs_leidos}
  al_ingestar(codigos, ...)   -> corre la detección para lo recién ingestado (lo usa ingest_bases)
  en_riesgo(hoy=None)         -> licitaciones vigentes sin bases, con la ventana de visita corriendo
  pendientes_de_visita(...)   -> las que YA tienen visita detectada y siguen abiertas

  python visitas.py <CODIGO>     # detecta y guarda una
  python visitas.py --riesgo     # lista las que están en ventana de visita sin bases
"""
import json
import os
import pathlib
import time
from datetime import datetime

import bases
import db
import schema_v3

# Ventana de riesgo: días desde la publicación a partir de los cuales una licitación sin bases
# descargadas se considera en peligro. Las visitas suelen convocarse dentro de la primera semana.
DIAS_RIESGO = int(os.environ.get("LOVEO_VISITA_DIAS_RIESGO", "3"))
# Score mínimo para que valga la pena alertar. LEGACY: quedó del score de 6 dimensiones y sólo se
# usa cuando el embudo todavía no evaluó la licitación (triage_gate/triage_senal en NULL).
SCORE_MIN_RIESGO = int(os.environ.get("LOVEO_VISITA_SCORE_MIN", "60"))
# Filtrar por score hacía la alerta inservible: de 26 avisos, ~22 eran plazas, canchas, luminarias
# y veredas — fuera de core, con score alto porque la suma ponderada premia lo logístico. Una
# alerta que hay que filtrar a ojo no se lee, y la visita perdida es cara: dos licitaciones se
# cayeron este mes por no ir (1867-28-LR26 y 1057501-454-LE26). Ahora manda el embudo, que decide
# por motivo. `USAR_EMBUDO=0` vuelve al comportamiento viejo.
USAR_EMBUDO = os.environ.get("LOVEO_VISITA_USAR_EMBUDO", "1") == "1"
# Tope de documentos leídos por licitación. La visita se declara en las bases, no en el anexo 14.
MAX_DOCS = int(os.environ.get("LOVEO_VISITA_MAX_DOCS", "12"))
# Topes del BACKFILL por corrida (las de documentos nuevos no consumen presupuesto: son las que
# acaban de cambiar y son pocas). Se acota por CANTIDAD y por RELOJ, porque el costo real no lo
# manda el número de licitaciones sino cuántas traen un pliego escaneado: una con OCR puede tardar
# más que veinte con capa de texto. Sin el tope de reloj, la primera corrida sobre una carpeta
# grande convierte al cron diario en una corrida de OCR de horas.
MAX_BACKFILL = int(os.environ.get("LOVEO_VISITA_MAX_BACKFILL", "25"))
MAX_SEGUNDOS_BACKFILL = int(os.environ.get("LOVEO_VISITA_MAX_SEG", "120"))

# Nuestro propio Excel de análisis cita el pliego entero, incluida la cláusula de visita. Leerlo
# sería detectar nuestra propia salida: el detector se confirmaría a sí mismo sin fuente real.
_PREFIJOS_IGNORADOS = ("analisis_", "análisis_", "resumen_lote")
_EXT_IGNORADAS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".dwg", ".dxf", ".mp4", ".zip7"}

# Los que más probablemente contienen la cláusula, para gastar el presupuesto de lectura en ellos.
_PALABRAS_PLIEGO = ("base", "administrativ", "tecnic", "técnic", "pliego", "resol",
                    "term", "anexo", "aclara", "respuesta", "acta")


def caracter(vis):
    """Colapsa el dict de bases.visita_a_terreno() a un valor único y comparable.

    El orden importa: 'prohibida' gana sobre todo (si el pliego dice expresamente que no se
    contempla, eso manda sobre cualquier boilerplate), y 'obligatoria' gana sobre 'puntuada'
    porque es la que decide admisibilidad, no puntaje."""
    if not vis or not vis.get("menciona"):
        return "sin_visita"
    if vis.get("prohibida"):
        return "prohibida"
    if vis.get("obligatoria"):
        return "obligatoria"
    if vis.get("puntuada"):
        return "puntuada"
    return "voluntaria"


def urgencia(car):
    """Frase accionable para el tablero y el mail. None si no hay nada que hacer."""
    return {
        "obligatoria": "EXCLUYENTE: no asistir deja la oferta inadmisible",
        "puntuada": "PUNTUADA: no asistir cuesta puntaje",
        "voluntaria": "Voluntaria: conviene ir, no elimina",
    }.get(car)


def _prioridad_doc(nombre):
    """Ordena los documentos: primero los que suenan a pliego. Menor = se lee antes."""
    n = (nombre or "").lower()
    for i, p in enumerate(_PALABRAS_PLIEGO):
        if p in n:
            return i
    return len(_PALABRAS_PLIEGO)


def _rutas(codigo, c):
    """Rutas locales de los documentos de la licitación, filtradas y priorizadas."""
    filas = c.execute("SELECT nombre_archivo, ruta_local FROM documentos WHERE codigo=?",
                      (codigo,)).fetchall()
    utiles = []
    for f in filas:
        nombre = (f["nombre_archivo"] or "")
        low = nombre.lower()
        if low.startswith(_PREFIJOS_IGNORADOS) or pathlib.Path(low).suffix in _EXT_IGNORADAS:
            continue
        ruta = f["ruta_local"]
        if ruta and pathlib.Path(ruta).is_file():
            utiles.append((_prioridad_doc(nombre), nombre, ruta))
    utiles.sort()
    return [(n, r) for _, n, r in utiles[:MAX_DOCS]]


def detectar(codigo, c=None):
    """Lee los documentos ya registrados y devuelve el veredicto de visita. No escribe nada.

    Devuelve None si la licitación no tiene ningún documento legible (distinto de 'sin_visita',
    que significa que SÍ se leyó el pliego y no la menciona)."""
    if c is None:
        with db.conn() as c2:
            return detectar(codigo, c2)
    rutas = _rutas(codigo, c)
    if not rutas:
        return None
    textos, leidos, fallidos = [], [], []
    for nombre, ruta in rutas:
        try:
            res = bases.documento_a_texto(ruta)          # usa el caché de documentos.texto_cache
            t = (res or {}).get("texto") or ""
            if t.strip():
                textos.append(t)
                leidos.append(nombre)
        except Exception:                                 # un anexo ilegible no invalida el resto
            fallidos.append(nombre)
    if not textos:
        return None
    vis = bases.visita_a_terreno("\n".join(textos))
    car = caracter(vis)
    return {"caracter": car, "urgencia": urgencia(car),
            "fecha_txt": vis.get("fecha_literal"), "fragmento": vis.get("fragmento") or "",
            "docs_leidos": leidos, "docs_fallidos": fallidos}


def guardar(codigo, res, c=None):
    """Persiste el veredicto en licitaciones.visita_*. Registra evento sólo si hay visita."""
    if c is None:
        with db.conn() as c2:
            return guardar(codigo, res, c2)
    c.execute("UPDATE licitaciones SET visita_caracter=?, visita_fecha_txt=?, "
              "visita_fragmento=?, visita_detectada_at=? WHERE codigo=?",
              (res["caracter"], res.get("fecha_txt"), (res.get("fragmento") or "")[:400],
               db._now(), codigo))
    if res["caracter"] in ("obligatoria", "puntuada"):
        db.log_evento(c, codigo, "visita",
                      f"{res['urgencia']}" + (f" · fecha en el pliego: {res['fecha_txt']}"
                                              if res.get("fecha_txt") else ""))
    return res


def detectar_y_guardar(codigo):
    """Detecta y persiste en una sola llamada. None si no había documentos legibles."""
    schema_v3.migrate()
    with db.conn() as c:
        res = detectar(codigo, c)
        if res is None:
            return None
        return guardar(codigo, res, c)


def al_ingestar(con_documentos_nuevos, matcheados=(), max_backfill=None, max_segundos=None):
    """Corre la detección después de una ingesta de bases. Lo llama ingest_bases.

    `con_documentos_nuevos` son los códigos que registraron archivos en esta corrida: se detectan
    siempre, porque son exactamente los que acaban de cambiar. `matcheados` son todos los códigos
    con carpeta; de esos se rellenan sólo los que nunca se analizaron, acotados por presupuesto
    de cantidad y de reloj (ver MAX_BACKFILL / MAX_SEGUNDOS_BACKFILL).

    Nunca propaga excepciones: la detección de visita no puede voltear el pipeline de ingesta."""
    max_backfill = MAX_BACKFILL if max_backfill is None else max_backfill
    max_segundos = MAX_SEGUNDOS_BACKFILL if max_segundos is None else max_segundos
    nuevos = list(dict.fromkeys(con_documentos_nuevos or []))
    pendientes = []
    try:
        schema_v3.migrate()
        with db.conn() as c:
            faltantes = {r["codigo"] for r in c.execute(
                "SELECT codigo FROM licitaciones WHERE visita_caracter IS NULL")}
        pendientes = [cod for cod in (matcheados or []) if cod in faltantes and cod not in nuevos]
    except Exception:
        pass
    cupo = pendientes[:max_backfill]

    detectadas, con_visita, sin_docs, hechos_backfill = 0, [], 0, 0
    arranque = time.monotonic()
    for i, cod in enumerate(nuevos + cupo):
        en_backfill = i >= len(nuevos)
        if en_backfill and time.monotonic() - arranque > max_segundos:
            break                              # se acabó el reloj: el resto queda para mañana
        try:
            res = detectar_y_guardar(cod)
        except Exception:                      # un pliego roto no frena la ingesta del resto
            continue
        finally:
            if en_backfill:
                hechos_backfill += 1
        if res is None:
            sin_docs += 1
            continue
        detectadas += 1
        if res["caracter"] in ("obligatoria", "puntuada"):
            con_visita.append({"codigo": cod, "caracter": res["caracter"],
                               "fecha_txt": res.get("fecha_txt"), "urgencia": res["urgencia"]})
    return {"detectadas": detectadas, "con_visita": con_visita, "sin_documentos": sin_docs,
            "segundos": round(time.monotonic() - arranque, 1),
            "backfill_pendiente": max(0, len(pendientes) - hechos_backfill)}


# --------------------------- alertas ---------------------------------------

def _fecha_publicacion(json_detalle, fallback=None):
    """FechaPublicacion del detalle del API (poblada en el 100% de los casos medidos).
    `fecha_descubierta` es el fallback: run_daily corre a diario, así que difiere poco."""
    try:
        d = json.loads(json_detalle) if json_detalle else {}
        f = (d.get("Fechas") or {}).get("FechaPublicacion")
        if f:
            return str(f)[:19]
    except (ValueError, TypeError, AttributeError):
        pass
    return str(fallback)[:19] if fallback else None


def _dias_desde(valor, hoy):
    if not valor:
        return None
    try:
        return (hoy.date() - datetime.fromisoformat(str(valor).replace(" ", "T")[:19]).date()).days
    except ValueError:
        return None


def _dias_hasta(valor, hoy):
    d = _dias_desde(valor, hoy)
    return None if d is None else -d


def en_riesgo(hoy=None, dias_min=None, score_min=None, limite=50):
    """Vigentes, sin bases descargadas y ya dentro de la ventana en que suele caer la visita.

    Es la alerta que faltaba: cuando no hay bases no se puede leer el pliego, así que no se puede
    saber si hay visita — y precisamente por eso hay que avisar. El silencio no es 'no hay visita',
    es 'no lo sabemos y el reloj corre'.

    QUIÉN ENTRA. Manda el EMBUDO (`triage_gate IS NULL` = sobrevive los tres gates), no el score.
    Con el score, de 26 alertas ~22 eran plazas, canchas, luminarias y veredas: la suma ponderada
    les daba 60-84 por lo logístico aunque estuvieran fuera de core. Una alerta que hay que
    filtrar a ojo deja de leerse, y ese es el peor final para un aviso que existe justamente
    porque perder una visita descalifica."""
    hoy = hoy or datetime.now()
    dias_min = DIAS_RIESGO if dias_min is None else dias_min
    score_min = SCORE_MIN_RIESGO if score_min is None else score_min
    schema_v3.migrate()
    # El embudo decide; el score sólo entra si la licitación todavía no pasó por el embudo.
    filtro = ("  AND (triage_senal IS NOT NULL OR triage_gate IS NOT NULL)"
              "  AND triage_gate IS NULL " if USAR_EMBUDO
              else "  AND COALESCE(score_provisional,0) >= ? ")
    params = () if USAR_EMBUDO else (score_min,)
    out = []
    with db.conn() as c:
        filas = c.execute(
            "SELECT codigo, nombre, organismo, comuna, region, monto_estimado, fecha_cierre, "
            "       score_provisional, docs_estado, json_detalle, fecha_descubierta, "
            "       triage_motivo, triage_confianza "
            "FROM licitaciones "
            "WHERE vigente_oferta=1 AND admisible=1 "
            "  AND estado_revision NOT IN ('descartada','aprobada') "
            "  AND (docs_estado IS NULL OR docs_estado != 'descargado') "
            + filtro, params).fetchall()
        for f in filas:
            pub = _fecha_publicacion(f["json_detalle"], f["fecha_descubierta"])
            d_pub = _dias_desde(pub, hoy)
            d_cierre = _dias_hasta(f["fecha_cierre"], hoy)
            if d_pub is None or d_pub < dias_min:
                continue
            if d_cierre is not None and d_cierre < 0:      # ya cerró: no es una alerta, es historia
                continue
            out.append({"codigo": f["codigo"], "nombre": f["nombre"], "organismo": f["organismo"],
                        "comuna": f["comuna"], "region": f["region"],
                        "monto": f["monto_estimado"], "score": f["score_provisional"],
                        "senal": f["triage_motivo"], "confianza": f["triage_confianza"],
                        "fecha_cierre": f["fecha_cierre"], "dias_publicada": d_pub,
                        "dias_al_cierre": d_cierre,
                        "motivo": f"Publicada hace {d_pub} días y sin bases descargadas: "
                                  "si convoca visita, la ventana puede estar corriendo."})
    # Primero lo que cierra antes; a igual cierre, lo que lleva más tiempo publicado sin bases.
    out.sort(key=lambda r: (r["dias_al_cierre"] if r["dias_al_cierre"] is not None else 9999,
                            -r["dias_publicada"]))
    return out[:limite]


def pendientes_de_visita(hoy=None, limite=50):
    """Las que YA tienen visita detectada en el pliego, siguen abiertas y no están descartadas.
    A diferencia de `en_riesgo`, acá el dato existe: lo que falta es ir."""
    hoy = hoy or datetime.now()
    schema_v3.migrate()
    out = []
    with db.conn() as c:
        filas = c.execute(
            "SELECT codigo, nombre, organismo, comuna, fecha_cierre, score_provisional, "
            "       visita_caracter, visita_fecha_txt, visita_fragmento "
            "FROM licitaciones "
            "WHERE vigente_oferta=1 AND visita_caracter IN ('obligatoria','puntuada') "
            "  AND estado_revision NOT IN ('descartada')").fetchall()
        for f in filas:
            d_cierre = _dias_hasta(f["fecha_cierre"], hoy)
            if d_cierre is not None and d_cierre < 0:
                continue
            out.append({"codigo": f["codigo"], "nombre": f["nombre"], "organismo": f["organismo"],
                        "comuna": f["comuna"], "score": f["score_provisional"],
                        "fecha_cierre": f["fecha_cierre"], "dias_al_cierre": d_cierre,
                        "caracter": f["visita_caracter"], "urgencia": urgencia(f["visita_caracter"]),
                        "fecha_txt": f["visita_fecha_txt"],
                        "fragmento": (f["visita_fragmento"] or "")[:300]})
    out.sort(key=lambda r: (0 if r["caracter"] == "obligatoria" else 1,
                            r["dias_al_cierre"] if r["dias_al_cierre"] is not None else 9999))
    return out[:limite]


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if args and args[0] == "--riesgo":
        print(json.dumps(en_riesgo(), indent=2, ensure_ascii=False, default=str))
    elif args and args[0] == "--pendientes":
        print(json.dumps(pendientes_de_visita(), indent=2, ensure_ascii=False, default=str))
    elif args:
        print(json.dumps(detectar_y_guardar(args[0]), indent=2, ensure_ascii=False, default=str))
    else:
        print(__doc__)
