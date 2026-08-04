"""
bases.py — Capa C (parte 1): convierte el PDF de las bases a TEXTO, local.
NO manda imágenes a la API: extrae texto con pdfplumber y, solo si una página no tiene
capa de texto (escaneada), cae a OCR local (pytesseract). Así se paga ~1/3 de los tokens
y no se choca con el tope de 100 páginas / 32 MB del modo PDF nativo.

  pdf_a_texto(ruta)        -> {"paginas":[...], "texto": str, "ocr_paginas":[...], "n_paginas":int}
  secciones(texto)         -> dict {seccion: fragmento}  (recorte por encabezados típicos de bases)
  texto_para_analisis(ruta, max_chars) -> texto recortado a las secciones relevantes (lo que se manda a Claude)

OCR es opcional: si pytesseract/pdf2image no están, se omite y se avisa (no rompe).
"""
import re
import unicodedata
from pathlib import Path
import pdfplumber


MIN_CHARS_PAGINA = 40   # bajo esto, la página se considera "sin texto" → candidata a OCR

# Encabezados típicos en bases de Mercado Público → secciones que alimentan el score y el Q&A.
SECCIONES = {
    "presupuesto":   r"(presupuesto|monto\s+disponible|monto\s+estimado|valor\s+referencial|financiamiento)",
    "plazo":         r"(plazo\s+de\s+entrega|plazo\s+de\s+ejecuci|plazo\s+del\s+contrato|plazo\s+de\s+fabricaci)",
    "garantias":     r"(garant[ií]a|boleta|seriedad\s+de\s+la\s+oferta|fiel\s+cumplimiento)",
    "evaluacion":    r"(criterios?\s+de\s+evaluaci|pauta\s+de\s+evaluaci|ponderaci)",
    "requisitos":    r"(requisitos|antecedentes\s+t[eé]cnicos|experiencia|profesional\s+residente|admisibilidad)",
    "visita":        r"(visita\s+a\s+terreno|visita\s+t[eé]cnica)",
    "subcontrato":   r"(subcontrat)",
    "anticipo":      r"(anticipo|estado\s+de\s+pago|forma\s+de\s+pago)",
}




def _ocr_pagina(page):
    """OCR opcional de una página pdfplumber. Devuelve texto o '' si no hay OCR disponible."""
    try:
        import pytesseract
        from PIL import Image
        im = page.to_image(resolution=200).original  # PIL Image
        return pytesseract.image_to_string(im, lang="spa")
    except Exception:
        return ""


def pdf_a_texto(ruta):
    ruta = str(ruta)
    paginas, ocr_pgs = [], []
    with pdfplumber.open(ruta) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            t = page.extract_text() or ""
            if len(t.strip()) < MIN_CHARS_PAGINA:        # página sin capa de texto → OCR
                ocr = _ocr_pagina(page)
                if ocr.strip():
                    t = ocr
                    ocr_pgs.append(i)
            paginas.append(t)
    return {"paginas": paginas, "texto": "\n".join(paginas),
            "ocr_paginas": ocr_pgs, "n_paginas": len(paginas)}


def _normalizar_con_mapa(s):
    """(texto_normalizado, mapa) para buscar encabezados y poder volver al texto ORIGINAL.

    `textnorm.na` (encode ascii+ignore) BORRA lo no representable (viñetas, dashes, comillas
    tipográficas, °…) y las ligaduras ('ﬁ') expanden a 2 chars: en ambos casos los offsets del
    normalizado NO coinciden con los del original, y recortar con ellos devolvía secciones corridas.
    Acá se normaliza sin restricción de longitud y `mapa[i]` guarda el índice ORIGINAL que produjo
    el char i del normalizado, así el recorte siempre cae en el lugar correcto."""
    out, mapa = [], []
    for i, ch in enumerate(s or ""):
        d = unicodedata.normalize("NFKD", ch)
        base = "".join(c for c in d if not unicodedata.combining(c)) or ch
        for c in base.lower():                    # 'ﬁ' → 'f','i' (ambos apuntan al mismo índice)
            out.append(c)
            mapa.append(i)
    mapa.append(len(s or ""))                     # centinela: fin del texto
    return "".join(out), mapa


def secciones(texto):
    """Parte el texto por encabezados relevantes; cada sección = desde su match hasta el siguiente.
    Busca sobre el texto normalizado y traduce las posiciones al ORIGINAL vía el mapa de offsets."""
    n, mapa = _normalizar_con_mapa(texto)
    hits = []
    for nombre, pat in SECCIONES.items():
        m = re.search(pat, n)
        if m:
            hits.append((m.start(), nombre))
    hits.sort()
    out = {}
    for idx, (pos, nombre) in enumerate(hits):
        ini = mapa[pos]                                     # posición en el texto ORIGINAL
        fin = (mapa[hits[idx + 1][0]] if idx + 1 < len(hits)
               else min(len(texto), ini + 2500))
        out[nombre] = texto[ini:fin].strip()
    return out


def texto_para_analisis(ruta, max_chars=12000):
    """Texto recortado a las secciones relevantes — esto es lo que se manda a Claude (no el PDF)."""
    full = pdf_a_texto(ruta)
    secs = secciones(full["texto"])
    if secs:
        armado = "\n\n".join(f"### {k.upper()}\n{v}" for k, v in secs.items())
    else:
        armado = full["texto"]          # sin encabezados reconocidos → texto completo (se recorta abajo)
    return {"texto": armado[:max_chars], "n_paginas": full["n_paginas"],
            "ocr_paginas": full["ocr_paginas"], "secciones_halladas": list(secs.keys())}


if __name__ == "__main__":
    import sys, json
    ruta = sys.argv[1] if len(sys.argv) > 1 else "calibration/ficha_real_2450-56-LE26.pdf"
    r = pdf_a_texto(ruta)
    print(f"Páginas: {r['n_paginas']} | OCR usado en: {r['ocr_paginas'] or 'ninguna'} | chars: {len(r['texto'])}")
    secs = secciones(r["texto"])
    print("Secciones detectadas:", list(secs.keys()))
    print("\n--- muestra (primeros 600 chars) ---\n", r["texto"][:600])
