"""
capa_c.py — Capa C (parte 2): análisis de bases con Claude. SOLO TEXTO (nunca el PDF como imagen).
Usa bases.py para extraer y recortar; manda el texto recortado a la API y devuelve:
  - extracción estructurada (presupuesto, plazo, garantías, criterios+pesos, requisitos, subcontrato, anticipo)
    → alimenta las dimensiones pendientes del score (complejidad; y el techo de presupuesto para margen).
  - Q&A N3 sobre el contenido de las bases.

API key: SOLO desde el entorno (ANTHROPIC_API_KEY) o config_local.API_KEY. NUNCA hardcodeada.
Modelo: barato por defecto (Haiku) porque se leen muchas bases; configurable.

  python capa_c.py --pdf calibration/ficha_real_2450-56-LE26.pdf            # analiza (necesita API key)
  python capa_c.py --pdf ... --dry                                          # NO llama API: muestra prompt + tokens
  python capa_c.py --codigo 2450-56-LE26 --pregunta "¿Qué garantía exige?"  # Q&A N3 (docs ya descargados)
"""
import os, sys, json, argparse
import bases

MODEL = os.environ.get("LOVEO_MODEL", "claude-haiku-4-5")   # barato para lectura masiva; subir a sonnet si hace falta

SYSTEM_EXTRACT = (
    "Sos un analista de licitaciones de Mercado Público (Chile) para una empresa de construcción modular en acero. "
    "Te paso el TEXTO de las bases (ya extraído). Devolvé SOLO un JSON, sin texto extra, con estas claves: "
    "presupuesto_clp (número o null), plazo_entrega_dias (número o null), "
    "garantias (lista de {tipo, monto_o_pct}), criterios_evaluacion (lista de {nombre, peso_pct}), "
    "requisitos_clave (lista de strings: profesional residente, visita obligatoria, certificados, experiencia mínima, etc.), "
    "subcontratacion_prohibida (true/false/null), anticipo (true/false/null), "
    "señales_complejidad (lista de strings: especialidades que exigen subcontrato, obra en sitio, etc.), "
    "materiales (lista de {partida, grupo, descripcion, cantidad, unidad}: un BORRADOR de cubicación "
    "con los materiales/partidas que el proyecto requiere según las especificaciones técnicas — "
    "grupo ∈ {material, mano_obra, transporte, otros}; cantidad es un número estimado o null; "
    "unidad ej. m2, ml, unidad, kg, gl. Estimá desde las especificaciones; si no hay datos para una "
    "cantidad, dejala en null. Es un borrador para curar, no una cotización), "
    "resumen (1-2 frases). Si un dato no está en el texto, poné null. No inventes."
)


def _client():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        try:
            from config_local import API_KEY as key  # opcional
        except Exception:
            key = None
    if not key:
        raise RuntimeError("Falta ANTHROPIC_API_KEY (export ANTHROPIC_API_KEY=... o config_local.API_KEY).")
    import anthropic
    return anthropic.Anthropic(api_key=key)


def _estimar_tokens(txt):       # estimación grosera sin llamar a la API (≈4 chars/token)
    return len(txt) // 4


def analizar_bases(pdf=None, codigo=None, dry=False):
    rutas = []
    if pdf:
        rutas = [pdf]
    elif codigo:
        import db
        with db.conn() as c:
            rutas = [r[0] for r in c.execute(
                "SELECT ruta_local FROM documentos WHERE codigo=?", (codigo,)).fetchall()]
        if not rutas:
            return {"error": f"Sin documentos descargados para {codigo}. Corré download.py (Capa B) primero."}
    bloques = []
    meta = []
    for r in rutas:
        ex = bases.texto_para_analisis(r, max_chars=12000)
        bloques.append(ex["texto"])
        meta.append({"archivo": r, "paginas": ex["n_paginas"],
                     "ocr": ex["ocr_paginas"], "secciones": ex["secciones_halladas"]})
    texto = "\n\n=====\n\n".join(bloques)

    if dry:
        return {"DRY_RUN": True, "modelo": MODEL, "tokens_estimados_entrada": _estimar_tokens(texto + SYSTEM_EXTRACT),
                "meta": meta, "muestra_texto": texto[:500]}

    client = _client()
    msg = client.messages.create(
        model=MODEL, max_tokens=1500, system=SYSTEM_EXTRACT,
        messages=[{"role": "user", "content": f"BASES:\n{texto}"}])
    raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(raw)
    except Exception:
        data = {"_parse_error": True, "raw": raw[:800]}
    return {"modelo": MODEL, "meta": meta, "extraccion": data}


def preguntar(codigo=None, pdf=None, pregunta="", dry=False):
    """Q&A N3 sobre el contenido de las bases (solo texto)."""
    ruta = pdf
    if not ruta and codigo:
        import db
        with db.conn() as c:
            row = c.execute("SELECT ruta_local FROM documentos WHERE codigo=? LIMIT 1", (codigo,)).fetchone()
        ruta = row[0] if row else None
    if not ruta:
        return {"error": "Sin documento para responder. Descargá las bases (Capa B) o pasá --pdf."}
    ex = bases.texto_para_analisis(ruta, max_chars=14000)
    sys_p = ("Respondé la pregunta SOLO con lo que diga el texto de las bases. "
             "Si no está, decí 'No aparece en las bases'. Sé breve y citá la sección.")
    if dry:
        return {"DRY_RUN": True, "modelo": MODEL,
                "tokens_estimados_entrada": _estimar_tokens(ex["texto"] + pregunta + sys_p)}
    client = _client()
    msg = client.messages.create(
        model=MODEL, max_tokens=600, system=sys_p,
        messages=[{"role": "user", "content": f"BASES:\n{ex['texto']}\n\nPREGUNTA: {pregunta}"}])
    return {"modelo": MODEL, "respuesta": "".join(b.text for b in msg.content if getattr(b, "type", "") == "text"),
            "fuente": "⛁ bases (Capa C)"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf"); ap.add_argument("--codigo"); ap.add_argument("--pregunta")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    if a.pregunta:
        print(json.dumps(preguntar(codigo=a.codigo, pdf=a.pdf, pregunta=a.pregunta, dry=a.dry), indent=2, ensure_ascii=False))
    else:
        print(json.dumps(analizar_bases(pdf=a.pdf, codigo=a.codigo, dry=a.dry), indent=2, ensure_ascii=False))
