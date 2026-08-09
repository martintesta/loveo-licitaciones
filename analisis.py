"""
analisis.py — Arma los DATOS del análisis integral de una licitación (lo que consume excel_analisis.py).

Híbrido, a propósito:
  - DETERMINISTA (de la base): meta, presupuesto, parámetros del modelo financiero, cubicación
    preciada, scoring 6-D, competencia (competidores/participaciones/adjudicaciones), info faltante.
    Esto NO lo decide un modelo: sale del mismo pipeline que muestra el tablero, así que el Excel
    nunca puede contradecir a la UI.
  - IA: lo que la base no tiene y hay que leer de las bases — objeto/alineación, compras, riesgos
    con mitigación y costo, RACI, estrategia, y la matriz de evaluación con sus escalones (lo que
    alimenta la hoja «Estrategia Ganar»). Son DOS llamadas sobre el MISMO prefijo cacheado, no una:
    el esquema completo no compila como gramática ("compiled grammar is too large"), así que se
    parte en licitación / matriz de evaluación. La segunda lee el digest de caché (~0,1×).

Si la llamada a la IA falla (sin API key, sin red, JSON ilegible), NO rompe: se cae a plantillas y
el Excel igual se genera con las hojas que sí tienen datos. Un análisis parcial vale más que un error.

  datos(codigo, enriquecer=None) -> dict con el esquema de excel_analisis.construir()
  precios_catalogo()             -> catálogo interno {descripcion_norm: {...}} (precios reales Loveo)

`enriquecer` es inyectable: los tests pasan una función pura y no tocan la red.
"""
import datetime
import json
import os

import cubicacion
import cubicacion_ia
import db
import digest
import scoring

# --- Modelo financiero (MODELO_FINANCIERO.md de la skill). Overridable desde config_local. -------
# La relación entre markup y los "techos de costo" del consolidado NO es libre:
#   costo base máx. SANO   = techo / markup_obj / (1+sobrecosto) = techo / 1.45 / 1.30 = techo / 1,885
#   costo base máx. LÍMITE = techo / markup_min / (1+sobrecosto) = techo / 1.25 / 1.30 = techo / 1,625
# Si alguien toca markup_obj/markup_min/sobrecosto, esos factores se mueven solos (y el test lo guarda).
PARAMS = {
    "sobrecosto": 0.30,
    "markup_min": 1.25,
    "markup_obj": 1.45,
    "margen_min": 0.25,
    "tasa_financiamiento": 0.10,
    "ppm": 0.02,
    "impuesto_renta": 0.25,
    "estructura_mensual": 17_800_000,
}
try:
    from config import PARAMS_FINANCIEROS as _P_CFG
    if _P_CFG:
        PARAMS.update(_P_CFG)
except (ImportError, AttributeError):
    pass

FACTOR_SANO = round(PARAMS["markup_obj"] * (1 + PARAMS["sobrecosto"]), 3)     # 1.885
FACTOR_LIMITE = round(PARAMS["markup_min"] * (1 + PARAMS["sobrecosto"]), 3)   # 1.625

MODEL = os.environ.get("LOVEO_MODEL_ANALISIS", "claude-opus-5")
# El presupuesto de salida lo comparten el thinking adaptativo y el JSON. Medido sobre una
# licitación real: 16.000 no alcanzaba y el JSON salía cortado a la mitad (JSONDecodeError), así que
# hay que dejar holgura de sobra. Si igual se corta, `_pedir` lo dice con todas las letras.
MAX_TOKENS = int(os.environ.get("LOVEO_ANALISIS_MAX_TOKENS", "32000"))

# RACI por defecto de Loveo (la IA la ajusta; si no corre, esta es la que va).
RACI_BASE = [
    {"item": "Decisión GO/NO-GO", "martin": "A", "pablo": "C", "valentina": "C"},
    {"item": "Cubicación y EETT", "martin": "I", "pablo": "C", "valentina": "R"},
    {"item": "Cotización de materiales", "martin": "I", "pablo": "R", "valentina": "C"},
    {"item": "Visita a terreno", "martin": "I", "pablo": "R", "valentina": "C"},
    {"item": "Armado de anexos administrativos", "martin": "A", "pablo": "R", "valentina": "I"},
    {"item": "Precio final de la oferta", "martin": "R", "pablo": "C", "valentina": "I"},
    {"item": "Carga de la oferta en Mercado Público", "martin": "A", "pablo": "R", "valentina": "I"},
]


def _lista(v):
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v.strip():
        return [v.strip()]
    return []


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ catálogo de precios reales
def precios_catalogo():
    """Último precio conocido por material. Es la fuente de la cubicación: los precios REALES que
    Loveo pagó (proyecto Talagante) + los que mantiene al día el refresco mensual de `precios.py`.
    Delega en `precios.catalogo()` para que el análisis y el job de precios no puedan discrepar
    sobre cuál es "el precio vigente" de un material."""
    import precios
    return precios.catalogo()


def _preciar_desde_catalogo(items, cat):
    """Completa el precio de cada partida desde el catálogo interno cuando falte. Devuelve
    (items, n_desde_catalogo). No inventa: si no hay match, la partida queda sin precio y eso
    se reporta en INFO FALTANTE."""
    n = 0
    for it in items:
        if _num(it.get("precio_unitario")):
            continue
        m = cat.get(cubicacion._na(it.get("partida") or it.get("descripcion") or ""))
        if m:
            it["precio_unitario"] = m["precio_unitario"]
            it["notas"] = " · ".join(x for x in [it.get("notas"), f"precio catálogo ({m['fuente']})"] if x)
            n += 1
    return items, n


# ------------------------------------------------------------------ parte determinista (la base)
def _meta(codigo, lic, hoy):
    km, base = scoring._dist_min(lic.get("region"))
    cierre = (lic.get("fecha_cierre") or "")[:10]
    dias = None
    if cierre:
        try:
            dias = (datetime.date.fromisoformat(cierre) - hoy).days
        except ValueError:
            dias = None
    return {
        "id": codigo, "nombre": lic.get("nombre") or "", "organismo": lic.get("organismo") or "",
        "comuna": lic.get("comuna") or "", "region": lic.get("region") or "",
        "fecha_publicacion": (lic.get("fecha_descubierta") or "")[:10],
        "fecha_cierre": cierre, "dias_restantes": dias if dias is not None else "",
        "fecha_analisis": hoy.isoformat(),
        "base_operativa": base or "", "distancia_km_base": km or 0,
    }


def _cubicacion(codigo, cat):
    """Cubicación desde lo que el pipeline ya curó (cubicacion_ia.borrador), preciada con el
    catálogo interno. Devuelve (filas, sin_precio, desde_catalogo)."""
    items = []
    for it in cubicacion_ia.borrador(codigo):
        items.append({"partida": it.get("descripcion") or it.get("partida") or "",
                      "unidad": it.get("unidad") or "",
                      "cantidad": _num(it.get("cantidad")) or 0,
                      "precio_unitario": _num(it.get("precio_unitario")) or 0,
                      "notas": it.get("precio_fuente") or ""})
    items, n_cat = _preciar_desde_catalogo(items, cat)
    sin_precio = [it["partida"] for it in items if not it["precio_unitario"] or not it["cantidad"]]
    return items, sin_precio, n_cat


def _scoring(sj):
    dims = (sj or {}).get("dimensiones") or {}
    return {k: (dims.get(k) or {}).get("score", 5) for k in scoring.PESOS}


def _competencia(codigo, organismo):
    """Censo de competencia REAL desde la base: quiénes participaron antes contra este organismo y
    con qué resultado. No inventa probabilidades — sin `p_eett` la hoja «Estrategia Ganar» corre su
    Monte Carlo con supuestos declarados, no con un censo falso (ver excel_analisis.usa_censo).

    `competidores`/`participaciones`/`adjudicaciones` las crea schema_v2: en una base que todavía no
    corrió esa migración simplemente no hay censo. Eso NO puede matar el análisis entero — es una
    hoja opcional, así que se devuelve None y el resto del informe sale igual."""
    try:
        with db.conn() as c:
            rivales = [dict(r) for r in c.execute(
                "SELECT co.razon_social AS nombre, co.rut AS rut, co.desde_anio AS desde, "
                "       COUNT(p.id) AS n, SUM(CASE WHEN p.resultado='ganada' THEN 1 ELSE 0 END) AS ganadas, "
                "       SUM(COALESCE(p.monto,0)) AS monto "
                "FROM competidores co JOIN participaciones p ON p.rut = co.rut "
                "GROUP BY co.rut, co.razon_social, co.desde_anio ORDER BY ganadas DESC, n DESC LIMIT 12"
            ).fetchall()]
            bench = [dict(r) for r in c.execute(
                "SELECT l.codigo AS id, l.nombre AS objeto, l.monto_estimado AS presupuesto, "
                "       a.n_oferentes AS oferentes "
                "FROM licitaciones l JOIN adjudicaciones a ON a.codigo = l.codigo "
                "WHERE l.organismo = ? AND l.codigo <> ? ORDER BY a.fecha DESC LIMIT 10",
                (organismo or "", codigo)).fetchall()]
    except Exception:                     # tablas de schema_v2 ausentes: sin censo, no sin informe
        return None
    if not rivales:
        return None
    empresas = [{"nombre": r["nombre"] or r["rut"], "rubro": "", "antiguedad": (str(r["desde"]) if r["desde"] else ""),
                 "adjudicaciones_n": r["ganadas"] or 0, "adjudicaciones_monto": r["monto"] or 0,
                 "historial_comprador": f"{r['n']} participaciones registradas",
                 "le_falta": "", "amenaza": ("ALTA" if (r["ganadas"] or 0) >= 3 else
                                             "MEDIA" if (r["ganadas"] or 0) >= 1 else "BAJA"),
                 "nota": ""} for r in rivales]
    return {"fuente_censo": "participaciones históricas registradas en la base (no acta de visita)",
            "total_asistentes": "—", "empresas": empresas,
            "benchmark_comprador": [{"id": b["id"], "objeto": b["objeto"], "presupuesto": b["presupuesto"],
                                     "oferentes": b["oferentes"] or "—", "adjudicado": None,
                                     "lectura": ""} for b in bench]}


def _criterios_desde_capa_c(ex):
    """Criterios de evaluación tal como los extrajo la Capa C: {nombre, peso_pct}. Sirven de piso si
    la IA no corre — sin escalones no hay simulación, pero la anatomía de la matriz igual se ve."""
    out = []
    for cr in _lista(ex.get("criterios_evaluacion")):
        if not isinstance(cr, dict):
            continue
        peso = _num(cr.get("peso_pct"))
        if peso is None:
            continue
        nombre = str(cr.get("nombre") or "").strip()
        es_precio = any(k in nombre.lower() for k in ("precio", "económic", "economic", "oferta econ"))
        out.append({"nombre": nombre or "Criterio", "peso": peso,
                    "tipo": "continuo" if es_precio else "binario",
                    "como_max": "", "costo_loveo": "", "controlable": ""})
    return out


# ------------------------------------------------------------------ parte IA (una sola llamada)
SYSTEM = (
    "Sos el analista de licitaciones públicas de Loveo Construcciones (Chile): construcción modular "
    "en acero — containers, módulos, baños y salas modulares, REAS/RESPEL. Bases operativas en Pirque "
    "(RM) y Puerto Montt.\n\n"
    "Te paso un DIGEST de las bases de una licitación (ya extraído y recortado) más el contexto que el "
    "sistema ya calculó. Producí el análisis integral que falta.\n\n"
    "Reglas:\n"
    "- No inventes cifras. Si un dato no está en el digest, dejalo vacío y anotalo en info_faltante.\n"
    "- La CUBICACIÓN se arma con los precios reales del catálogo que te paso. Usá la descripción EXACTA "
    "del catálogo cuando el material corresponda (así el sistema puede repreciarla sola). Solo agregá "
    "una partida fuera del catálogo si el proyecto la exige y no hay equivalente; en ese caso dejá "
    "precio_unitario en 0 y explicá en notas que falta cotizar.\n"
    "- En evaluacion.criterios: el criterio de PRECIO va con tipo 'continuo' y su fórmula. Los demás van "
    "'binario' (un escalón con todo el peso) o 'escalonado' (varios escalones). es_compuerta=true solo si "
    "no cumplirlo impide que abran el sobre económico. Las p_rival de cada criterio suman 1.0 y son tu "
    "estimación de qué fracción de los rivales alcanza cada escalón.\n"
    "- Los riesgos son los de ESTA licitación (plazo, garantías, visita excluyente, multas, logística por "
    "distancia), con mitigación concreta y su costo en pesos.\n"
    "- estrategia.texto es el veredicto en 3-5 frases: se gana o no, y por dónde."
)

_ESC = {"type": "object", "additionalProperties": False,
        "properties": {"pts": {"type": "number"}, "cond": {"type": "string"}, "p_rival": {"type": "number"}},
        "required": ["pts", "cond", "p_rival"]}

# Dos schemas y no uno: el esquema completo hace que la API rechace la request con "the compiled
# grammar is too large". Cada mitad entra holgada por separado, y el corte cae en un borde real:
#   LICITACION → qué se construye, qué cuesta y qué puede salir mal (hojas Cubicación..RACI)
#   EVALUACION → cómo se reparte el puntaje (hoja «Estrategia Ganar»)
# Bonus: son independientes, así que si una falla la otra igual entrega.
SCHEMA_LICITACION = {
    "type": "object", "additionalProperties": False,
    "required": ["objeto_alineacion", "cubicacion", "plazos", "compras", "riesgos", "raci",
                 "estrategia", "info_faltante"],
    "properties": {
        "objeto_alineacion": {
            "type": "object", "additionalProperties": False,
            "required": ["objeto", "familia", "alineacion_score", "alineacion_comentario", "referencia_competitiva"],
            "properties": {"objeto": {"type": "string"}, "familia": {"type": "string"},
                           "alineacion_score": {"type": "integer"},
                           "alineacion_comentario": {"type": "string"},
                           "referencia_competitiva": {"type": "string"}}},
        "cubicacion": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["partida", "unidad", "cantidad", "precio_unitario", "notas"],
            "properties": {"partida": {"type": "string"}, "unidad": {"type": "string"},
                           "cantidad": {"type": "number"}, "precio_unitario": {"type": "number"},
                           "notas": {"type": "string"}}}},
        "plazos": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["etapa", "dias"],
            "properties": {"etapa": {"type": "string"}, "dias": {"type": "integer"}}}},
        "compras": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["item", "proveedor", "lead_time", "precio_ref", "riesgo", "nota"],
            "properties": {"item": {"type": "string"}, "proveedor": {"type": "string"},
                           "lead_time": {"type": "string"}, "precio_ref": {"type": "number"},
                           "riesgo": {"type": "string"}, "nota": {"type": "string"}}}},
        "riesgos": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["categoria", "riesgo", "probabilidad", "impacto", "mitigacion",
                         "costo_mitigacion", "responsable"],
            "properties": {"categoria": {"type": "string"}, "riesgo": {"type": "string"},
                           "probabilidad": {"type": "string"}, "impacto": {"type": "string"},
                           "mitigacion": {"type": "string"}, "costo_mitigacion": {"type": "number"},
                           "responsable": {"type": "string"}}}},
        "raci": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["item", "martin", "pablo", "valentina"],
            "properties": {"item": {"type": "string"}, "martin": {"type": "string"},
                           "pablo": {"type": "string"}, "valentina": {"type": "string"}}}},
        "estrategia": {
            "type": "object", "additionalProperties": False,
            "required": ["texto", "precio_recomendado_pct"],
            "properties": {"texto": {"type": "string"}, "precio_recomendado_pct": {"type": "number"}}},
        "info_faltante": {"type": "array", "items": {"type": "string"}},
    },
}

SCHEMA_EVALUACION = {
    "type": "object", "additionalProperties": False,
    "required": ["evaluacion"],
    "properties": {
        "evaluacion": {
            "type": "object", "additionalProperties": False,
            "required": ["criterios", "no_evaluado", "reglas_estructurales", "supuestos_competencia",
                         "plan_accion"],
            "properties": {
                "criterios": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["nombre", "peso", "tipo", "formula", "como_max", "costo_loveo",
                                 "controlable", "es_compuerta", "escalones"],
                    "properties": {"nombre": {"type": "string"}, "peso": {"type": "number"},
                                   "tipo": {"type": "string", "enum": ["continuo", "binario", "escalonado"]},
                                   "formula": {"type": "string"}, "como_max": {"type": "string"},
                                   "costo_loveo": {"type": "string"}, "controlable": {"type": "string"},
                                   "es_compuerta": {"type": "boolean"},
                                   "escalones": {"type": "array", "items": _ESC}}}},
                "no_evaluado": {"type": "array", "items": {"type": "string"}},
                "reglas_estructurales": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["articulo", "regla", "consecuencia", "severidad"],
                    "properties": {"articulo": {"type": "string"}, "regla": {"type": "string"},
                                   "consecuencia": {"type": "string"},
                                   "severidad": {"type": "string",
                                                 "enum": ["critica", "alta", "media", "oportunidad"]}}}},
                "supuestos_competencia": {
                    "type": "object", "additionalProperties": False,
                    "required": ["n_competidores", "precio_rival_pct"],
                    "properties": {"n_competidores": {"type": "array", "items": {"type": "integer"}},
                                   "precio_rival_pct": {"type": "array", "items": {"type": "number"}}}},
                "plan_accion": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["prioridad", "accion", "asegura", "costo", "plazo", "responsable"],
                    "properties": {"prioridad": {"type": "string"}, "accion": {"type": "string"},
                                   "asegura": {"type": "string"}, "costo": {"type": "string"},
                                   "plazo": {"type": "string"}, "responsable": {"type": "string"}}}},
            }},
    },
}


def _cliente():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        try:
            from config_local import API_KEY as key
        except Exception:
            key = None
    if not key:
        raise RuntimeError("Falta ANTHROPIC_API_KEY: el análisis integral corre sin IA (hojas parciales).")
    import anthropic
    return anthropic.Anthropic(api_key=key)


TAREA_LICITACION = (
    "Analizá la licitación: objeto y alineación con Loveo, cubicación (desde el catálogo), plazos, "
    "plan de compras, riesgos con mitigación y costo, RACI (Martin/Pablo/Valentina), veredicto y "
    "% del techo a ofertar, y lo que falte para cerrar el análisis."
)
TAREA_EVALUACION = (
    "Desarmá la MATRIZ DE EVALUACIÓN de estas bases: cada criterio con su peso, su tipo (continuo "
    "para el precio; binario o escalonado para el resto), sus escalones con la probabilidad de que "
    "un rival alcance cada uno, y si es compuerta. Sumá lo que NO se evalúa (vale 0 puntos), las "
    "reglas estructurales fuera de la matriz (visitas excluyentes, causales de inadmisibilidad), "
    "los supuestos de competencia y el plan de acción ordenado por retorno."
)


def _pedir(cl, bloque_fijo, tarea, schema):
    """Una llamada con structured outputs. `bloque_fijo` va con cache_control: es el prefijo pesado
    (system + catálogo + digest) y las dos llamadas lo comparten, así la segunda lo lee de caché a
    ~0,1× en vez de re-pagarlo. Streaming porque el digest es largo y max_tokens alto: sin eso la
    request se pasa del timeout HTTP del SDK."""
    with cl.messages.stream(
        model=MODEL, max_tokens=MAX_TOKENS,
        system=[{"type": "text", "text": bloque_fijo, "cache_control": {"type": "ephemeral"}}],
        thinking={"type": "adaptive"},
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": tarea}],
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError("La API rechazó el análisis (stop_reason=refusal).")
    if msg.stop_reason == "max_tokens":
        # El JSON quedó cortado a la mitad. Sin este chequeo el síntoma es un JSONDecodeError
        # críptico y uno va a buscar el bug al schema, no al presupuesto de tokens.
        raise RuntimeError(
            f"La respuesta se cortó por max_tokens ({MAX_TOKENS}): el JSON quedó incompleto. "
            f"Subí LOVEO_ANALISIS_MAX_TOKENS.")
    return json.loads(next((b.text for b in msg.content if b.type == "text"), ""))


def _enriquecer_real(contexto, digest_txt, catalogo_txt):
    """DOS llamadas sobre el MISMO prefijo cacheado (ver SCHEMA_LICITACION/SCHEMA_EVALUACION: el
    esquema entero no compila como gramática). Son independientes: si la de la matriz falla, el
    análisis igual se entrega sin la hoja «Estrategia Ganar»."""
    cl = _cliente()
    fijo = (SYSTEM
            + "\n\n# CONTEXTO YA CALCULADO POR EL SISTEMA\n"
            + json.dumps(contexto, ensure_ascii=False, indent=1)
            + "\n\n# CATÁLOGO DE PRECIOS REALES DE LOVEO (usá estas descripciones exactas)\n"
            + catalogo_txt
            + "\n\n# DIGEST DE LAS BASES\n" + digest_txt)
    out = _pedir(cl, fijo, TAREA_LICITACION, SCHEMA_LICITACION)
    try:
        out.update(_pedir(cl, fijo, TAREA_EVALUACION, SCHEMA_EVALUACION))
    except Exception as e:
        out.setdefault("info_faltante", []).append(
            f"No se pudo desarmar la matriz de evaluación ({type(e).__name__}): sin hoja «Estrategia Ganar».")
    return out


def _catalogo_txt(cat, tope=120):
    filas = sorted(cat.values(), key=lambda r: -(r["precio_unitario"] or 0))[:tope]
    return "\n".join(f"- {r['descripcion']} | {r['unidad'] or 's/u'} | ${r['precio_unitario']:,.0f}"
                     .replace(",", ".") for r in filas) or "(catálogo vacío)"


# ------------------------------------------------------------------ ensamblado
def datos(codigo, enriquecer=None, hoy=None):
    """Dict completo para excel_analisis.construir(). `enriquecer(contexto, digest, catalogo)` es
    inyectable (tests sin red). Devuelve {"error": ...} si el código no existe."""
    hoy = hoy or datetime.date.today()
    with db.conn() as c:
        lic = c.execute("SELECT * FROM licitaciones WHERE codigo=?", (codigo,)).fetchone()
        if not lic:
            return {"error": f"No se encontró la licitación {codigo}."}
        lic = dict(lic)
        a = c.execute("SELECT * FROM analisis_bases WHERE codigo=? ORDER BY id DESC LIMIT 1",
                      (codigo,)).fetchone()
        analisis = dict(a) if a else {}
    ex = {}
    if analisis.get("json_extraccion"):
        try:
            ex = json.loads(analisis["json_extraccion"]) or {}
        except (ValueError, TypeError):
            ex = {}
    sj = {}
    if lic.get("score_json"):
        try:
            sj = json.loads(lic["score_json"]) or {}
        except (ValueError, TypeError):
            sj = {}

    cat = precios_catalogo()
    cub, sin_precio, n_cat = _cubicacion(codigo, cat)
    techo = analisis.get("presupuesto_clp") or lic.get("monto_estimado") or 0

    faltante = []
    if not techo:
        faltante.append("Presupuesto no publicado en el portal ni detectado en las bases.")
    if not analisis:
        faltante.append("Las bases todavía no pasaron por Capa C (sin extracción estructurada).")
    if not cub:
        faltante.append("Sin cubicación: no hay BOM curado para esta licitación.")
    if sin_precio:
        faltante.append(f"{len(sin_precio)} partida(s) sin precio o cantidad: "
                        + ", ".join(sin_precio[:5]) + ("…" if len(sin_precio) > 5 else ""))

    D = {
        "meta": _meta(codigo, lic, hoy),
        "presupuesto": {"monto_disponible": techo,
                        "neto_o_iva": "desconocido" if techo else "sin presupuesto publicado",
                        "notas": ""},
        "params": dict(PARAMS),
        "cubicacion": cub,
        "capital_adelantado": None,
        "scoring": _scoring(sj),
        "raci": list(RACI_BASE),
        "plazos": ([{"etapa": "Plazo de entrega (bases)", "dias": analisis["plazo_dias"]}]
                   if analisis.get("plazo_dias") else []),
        "compras": [],
        "riesgos": [],
        "objeto_alineacion": {"objeto": lic.get("descripcion") or lic.get("nombre") or "",
                              "familia": cubicacion_ia.tipo_producto(lic.get("nombre") or "") or "",
                              "alineacion_score": _scoring(sj).get("alineacion", 5),
                              "alineacion_comentario": "", "referencia_competitiva": ""},
        "estrategia": {"texto": analisis.get("resumen") or "", "precio_recomendado_pct": None},
        "info_faltante": faltante,
    }
    crit = _criterios_desde_capa_c(ex)
    if crit:
        D["evaluacion"] = {"criterios": crit, "no_evaluado": [], "reglas_estructurales": [],
                           "supuestos_competencia": {"n_competidores": [2, 6],
                                                     "precio_rival_pct": [0.78, 1.00]},
                           "plan_accion": []}
    comp = _competencia(codigo, lic.get("organismo"))
    if comp:
        D["competencia"] = comp

    # ---- capa IA: solo lo que la base no tiene. Cualquier fallo deja el análisis determinista intacto.
    enriquecer = enriquecer or _enriquecer_real
    contexto = {"meta": D["meta"], "presupuesto": D["presupuesto"], "params": D["params"],
                "scoring_6d": D["scoring"], "cubicacion_actual": cub,
                "extraccion_capa_c": ex, "info_faltante": faltante}
    try:
        dg = digest.para_analisis(codigo)
        if dg["ilegibles"]:
            D["info_faltante"].append("Documentos ilegibles pese al OCR: " + ", ".join(dg["ilegibles"]))
        ia = enriquecer(contexto, dg["digest"], _catalogo_txt(cat)) or {}
    except Exception as e:                      # sin API key / sin red / respuesta ilegible
        D["info_faltante"].append(f"Análisis con IA no disponible ({type(e).__name__}): las hojas de "
                                  f"Riesgos, Compras y Estrategia quedan sin contenido específico.")
        D["_ia"] = False
        return D

    D["_ia"] = True
    for k in ("compras", "riesgos", "plazos"):
        if ia.get(k):
            D[k] = ia[k]
    if ia.get("raci"):
        D["raci"] = ia["raci"]
    if ia.get("objeto_alineacion"):
        D["objeto_alineacion"].update({k: v for k, v in ia["objeto_alineacion"].items() if v not in (None, "")})
    if ia.get("estrategia"):
        D["estrategia"].update({k: v for k, v in ia["estrategia"].items() if v not in (None, "")})
    if ia.get("evaluacion", {}).get("criterios"):
        D["evaluacion"] = ia["evaluacion"]
    if ia.get("info_faltante"):
        D["info_faltante"] = list(dict.fromkeys(D["info_faltante"] + _lista(ia["info_faltante"])))
    # La cubicación de la IA solo se usa si no había una curada: la de Valentina/el usuario MANDA.
    if not cub and ia.get("cubicacion"):
        nuevos, _ = _preciar_desde_catalogo([dict(x) for x in ia["cubicacion"]], cat)
        D["cubicacion"] = nuevos
        faltan = [x["partida"] for x in nuevos if not _num(x.get("precio_unitario"))]
        if faltan:
            D["info_faltante"].append(f"{len(faltan)} partida(s) propuestas sin precio en el catálogo: "
                                      + ", ".join(faltan[:5]))
    return D


if __name__ == "__main__":
    import sys
    print(json.dumps(datos(sys.argv[1]), indent=2, ensure_ascii=False, default=str)[:6000])
