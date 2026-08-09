"""
digest.py — Reduce TODAS las bases de una licitación a un digest con lo que el análisis integral
necesita (informe.py). Es el paso previo a la única llamada al modelo.

Por qué existe teniendo `bases.secciones()`: esa función recorta las 8 secciones que alimentan el
score de la Capa C (presupuesto, plazo, garantías, evaluación, requisitos, visita, subcontrato,
anticipo). El análisis integral necesita además lo que decide la ESTRATEGIA: cómo se reparten los
puntajes escalón por escalón, causales de inadmisibilidad, empate, multas, el itemizado y las EETT
con dimensiones. Esas son las 16 reglas de abajo.

La extracción a texto NO se reimplementa: la hace `bases.documento_a_texto()`, que ya cachea en
`documentos.texto_cache`, OCRea las páginas escaneadas y sabe leer .pdf/.docx/.xlsx/.doc/.zip.

  extracto(codigo)  -> {"texto", "archivos": [...], "ocr": [...], "ilegibles": [...]}
  digerir(texto)    -> {"base": str, "tecnico": str}
  para_analisis(codigo) -> {"digest", "archivos", "ocr", "ilegibles", "chars"}

  python digest.py 1658-171-LE26
"""
import re

import bases
import db

# (etiqueta, patrón, líneas antes, líneas después, máx. bloques)
REGLAS = [
    ("OBJETO",      r"objeto de la (licitaci|propuesta)|se requiere la|denominad[oa]\s", 1, 6, 3),
    ("PRESUPUESTO", r"presupuesto\s+(disponible|referencial|m[aá]ximo|estimado)|"
                    r"monto\s+(disponible|m[aá]ximo|referencial|total\s+estimado)|asciende a la suma", 2, 6, 6),
    ("IVA",         r"iva\s+inclu|impuesto[s]?\s+inclu|valores?\s+netos?|sin\s+incluir\s+impuesto", 1, 3, 4),
    ("CRITERIOS",   r"criterios?\s+de\s+evaluaci|ponderaci[oó]n|tabla\s+de\s+evaluaci", 2, 40, 4),
    ("PUNTAJE",     r"puntaje|puntos?\s*=|se asignar[aá]n?\s+\d+\s*punto", 1, 6, 14),
    ("PLAZO",       r"plazo\s+de\s+(entrega|ejecuci|instalaci)|d[ií]as\s+corridos|"
                    r"d[ií]as\s+h[aá]biles\s+para\s+(la\s+)?entrega|tiempo\s+de\s+(entrega|ejecuci)", 1, 5, 10),
    ("GARANTIA",    r"garant[ií]a\s+de\s+(fiel|seriedad)|boleta\s+de\s+garant|5%\s+del\s+valor|"
                    r"garant[ií]a\s+t[eé]cnica|garant[ií]a\s+post", 1, 6, 8),
    ("VISITA",      r"visita\s+a\s+terreno|visita\s+t[eé]cnica|visita\s+obligatoria", 2, 6, 5),
    ("INADMISIBLE", r"inadmisib|quedar[aá]\s+fuera\s+de\s+bases|ser[aá]n?\s+rechazad|"
                    r"causal(es)?\s+de\s+exclusi", 1, 5, 8),
    ("SUBCONTRATA", r"subcontrat", 1, 4, 4),
    ("PAGO",        r"forma\s+de\s+pago|plazo[s]?\s+de\s+pago|se\s+pagar[aá]|estado[s]?\s+de\s+pago|"
                    r"30\s+d[ií]as\s+corridos", 1, 5, 6),
    ("EMPATE",      r"empate", 1, 5, 3),
    ("MULTAS",      r"multa", 1, 4, 4),
    ("ITEMIZADO",   r"itemizado|partida|cubicaci|presupuesto\s+detallado|planilla\s+de\s+precios", 1, 4, 8),
    ("EETT",        r"especificaci(ones)?\s+t[eé]cnicas?|dimensiones|medidas|m2|mt2|metros\s+cuadrados|"
                    r"espesor|aislaci|estructura", 0, 3, 22),
    ("EXPERIENCIA", r"experiencia", 1, 5, 6),
]

# Las etiquetas técnicas van a un digest aparte con tope más alto: son las que traen las cantidades
# (itemizado, EETT) y los escalones de puntaje. Mezcladas con el resto se las comía el recorte.
TECNICAS = {"EETT", "ITEMIZADO", "PUNTAJE", "EXPERIENCIA", "MULTAS"}
TOPE_BLOQUE = 450       # chars por bloque
TOPE_SECCION = 1200     # chars por etiqueta (secciones normales)
TOPE_TECNICO = 6000     # chars por etiqueta (secciones técnicas)


def _bloques(lineas, patron, antes, despues, maxb):
    """Bloques de contexto alrededor de cada match, sin solaparse entre sí."""
    rx = re.compile(patron, re.I)
    out, usados, n = [], set(), 0
    for i, ln in enumerate(lineas):
        if n >= maxb:
            break
        if not rx.search(ln):
            continue
        a, b = max(0, i - antes), min(len(lineas), i + despues + 1)
        if any(j in usados for j in range(a, b)):
            continue
        usados.update(range(a, b))
        out.append("\n".join(lineas[a:b]))
        n += 1
    return out


def digerir(texto):
    """Extracto completo → {"base", "tecnico"}. Puro (no toca la base ni el disco): testeable."""
    lineas = [ln.rstrip() for ln in (texto or "").split("\n")]
    archivos = [ln for ln in lineas if ln.startswith("### ARCHIVO:")]
    base = [f"### DIGEST (fuente: {len(archivos)} archivos, {len(texto or '')} chars) ###"] + archivos
    tecnico = ["### DIGEST TÉCNICO ###"]
    for etiqueta, pat, antes, despues, maxb in REGLAS:
        bs = _bloques(lineas, pat, antes, despues, maxb)
        if not bs:
            continue
        destino = tecnico if etiqueta in TECNICAS else base
        tope = TOPE_TECNICO if etiqueta in TECNICAS else TOPE_SECCION
        destino.append(f"\n\n########## {etiqueta} ##########")
        usado = 0
        for b in bs:
            b = re.sub(r"\n{2,}", "\n", b).strip()
            if not b:
                continue
            if len(b) > TOPE_BLOQUE:
                b = b[:TOPE_BLOQUE] + " …[recortado]"
            if usado + len(b) > tope:
                destino.append(f"[… {len(bs)} bloques, sección recortada]")
                break
            usado += len(b)
            destino.append("---\n" + b)
    return {"base": "\n".join(base), "tecnico": "\n".join(tecnico)}


def extracto(codigo):
    """Texto plano de TODOS los documentos registrados de la licitación, con encabezado por archivo.
    Reusa `bases.documento_a_texto` (caché + OCR + .docx/.xlsx/.zip). Un documento que revienta no
    frena al resto: se anota el error en el texto para que se vea en el digest."""
    with db.conn() as c:
        docs = [dict(r) for r in c.execute(
            "SELECT nombre_archivo, ruta_local FROM documentos WHERE codigo=? ORDER BY nombre_archivo",
            (codigo,)).fetchall()]
    partes = [f"### LICITACIÓN {codigo} — {len(docs)} documentos ###"]
    ocr, ilegibles = [], []
    for d in docs:
        nombre = d["nombre_archivo"] or "(sin nombre)"
        partes.append(f"\n\n{'=' * 70}\n### ARCHIVO: {nombre}\n{'=' * 70}")
        try:
            res = bases.documento_a_texto(d["ruta_local"])
        except Exception as e:                       # formato ilegible / archivo movido
            partes.append(f"[ERROR extrayendo: {type(e).__name__}: {e}]")
            ilegibles.append(nombre)
            continue
        if res.get("ocr_paginas"):
            ocr.append({"archivo": nombre, "paginas": res["ocr_paginas"]})
        if bases.calidad_texto(res["texto"]) < bases.CALIDAD_MINIMA:   # OCR que devolvió basura
            ilegibles.append(nombre)
        partes.append(res["texto"])
    return {"texto": "\n".join(partes), "archivos": [d["nombre_archivo"] for d in docs],
            "ocr": ocr, "ilegibles": ilegibles}


def para_analisis(codigo):
    """Lo que consume el prompt del análisis integral: digest base + digest técnico, más la
    trazabilidad de qué se leyó, qué salió por OCR y qué quedó ilegible (eso va a INFO FALTANTE)."""
    ex = extracto(codigo)
    d = digerir(ex["texto"])
    texto = d["base"] + "\n\n" + d["tecnico"]
    return {"digest": texto, "archivos": ex["archivos"], "ocr": ex["ocr"],
            "ilegibles": ex["ilegibles"], "chars": len(texto), "chars_fuente": len(ex["texto"])}


if __name__ == "__main__":
    import sys
    r = para_analisis(sys.argv[1])
    print(f"{len(r['archivos'])} archivos · fuente {r['chars_fuente']} chars → digest {r['chars']} chars")
    print(f"OCR: {r['ocr'] or 'ninguno'} · ilegibles: {r['ilegibles'] or 'ninguno'}")
    print(r["digest"][:2000])
