"""
montos.py — Extrae el PRESUPUESTO del pliego cuando el API lo deja en null.

`MontoEstimado` de Mercado Público viene vacío con frecuencia: de las licitaciones vivas de
agosto 2026 con bases descargadas, 4 de 9 figuraban "sin monto" — y las 4 traían la cifra escrita
en el pliego, sólo que con otro nombre: "presupuesto disponible", "presupuesto máximo total",
"presupuesto referencial", "asciende a la suma de". Sin ese número no hay techo, y sin techo no hay
margen que calcular: es el dato del que dependen los tres NO-GO de la semana.

  candidatos(texto)     -> [{valor, clave, fragmento, en_palabras, peso}] ordenados por peso
  del_pliego(codigo)    -> {monto, iva, fuente, confianza, alternativas} leyendo sus documentos
  al_ingestar(codigos)  -> escribe monto_estimado en las que estaban en null (lo llama ingest_bases)

  python montos.py 2775-85-LP26        # muestra qué encontró y con qué contexto, sin escribir
  python montos.py --faltantes         # las vigentes con bases y sin monto
"""
import os
import re

import db
import schema_v3

# Rango plausible para el techo de una licitación pública chilena. Fuera de esto NO es plata:
# por abajo son códigos y cantidades; por arriba, códigos de cuenta presupuestaria (el de Rengo
# era 215.29.99.999.092.001.01.01, del que se recortaba "99.999.092.001" = 99 mil millones).
MONTO_MIN = int(os.environ.get("LOVEO_MONTO_MIN", "500000"))
MONTO_MAX = int(os.environ.get("LOVEO_MONTO_MAX", "20000000000"))

# Palabras que anteceden al techo, de más específica a más genérica. El peso sale del orden.
CLAVES = [
    (r"presupuesto\s+(?:disponible|m[aá]ximo(?:\s+total)?|referencial|asignado|designado)", 10),
    (r"monto\s+(?:disponible|m[aá]ximo|referencial|total\s+disponible|de\s+adjudicaci[oó]n)", 10),
    (r"disponibilidad\s+presupuestaria(?:\s+m[aá]xima)?", 9),
    (r"valor\s+(?:referencial|total\s+estimado|m[aá]ximo)", 9),
    (r"asciende\s+a\s+la\s+(?:suma|cantidad)", 8),
    (r"presupuesto\s+estimado", 8),
    (r"certificado\s+de\s+disponibilidad", 6),
    (r"monto\s+estimado", 6),
    (r"financiamiento", 3),
    # Genérica y con sufijo abierto a propósito: los certificados y ábacos presupuestarios dicen
    # "Información Presupuestaria", no "presupuesto". Pesa poco; la filtran el rango y las guardas.
    (r"presupuest\w*", 3),
]
_RX_CLAVES = [(re.compile(p, re.I), w) for p, w in CLAVES]

# 174.914.000 · $ 40.000.000 · 38.558.352 — al menos dos grupos de tres (≥ 6 cifras).
RX_PLATA = re.compile(r"\d{1,3}(?:\.\d{3}){2,}")
# "ciento setenta y cuatro millones novecientos catorce mil pesos" — el pliego casi siempre repite
# la cifra en palabras, y esa repetición es la mejor confirmación de que se leyó bien el número.
RX_PALABRAS = re.compile(
    r"\b(?:un|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince|"
    r"dieci\w+|veinte|veinti\w+|treinta|cuarenta|cincuenta|sesenta|setenta|ochenta|noventa|"
    r"cien|ciento|doscientos|trescientos|cuatrocientos|quinientos|seiscientos|setecientos|"
    r"ochocientos|novecientos|mil)[\w\s]{0,80}?millones?", re.I)

RX_IVA_INC = re.compile(r"(?:iva|impuestos?)\s+inclu|inclu\w*\s+(?:el\s+)?(?:iva|impuestos?)|"
                        r"impuestos?\s+incluidos?", re.I)
RX_IVA_MAS = re.compile(r"m[aá]s\s+iva|\+\s*iva|valores?\s+netos?|sin\s+(?:iva|impuestos?)|neto\s+m[aá]s", re.I)

# --- las tres trampas --------------------------------------------------------
# RUT: 69.150.200-7 calza exactamente con el patrón de plata. El de Coelemu se colaba como
# "presupuesto de $69.150.200" en la primera versión de esto.
# Las dos clases de carácter están abiertas a propósito: el OCR devuelve el guión del dígito
# verificador como em-dash ("69.150.200—7") y el "N°" como "N*", y con las variantes estrictas
# la guarda no disparaba sobre el documento real.
RX_DV_RUT = re.compile(r"^\s*[-‐‑–—─]\s*[0-9kK]\b")
RX_ANTES_RUT = re.compile(r"(?:r\.?\s?u\.?\s?t\.?|rol\s+[uú]nico)\s*"
                          r"(?:n[°º*.º]{0,2})?\s*:?\s*$", re.I)
# Documento AJENO: la carpeta de una licitación puede tener papeles de otra. Pasó de verdad —
# el pliego de JUNJI ($97,4M) tenía adentro el decreto de Temuco ($22,6M), y sin esta guarda el
# extractor cargaba el techo equivocado con toda confianza.
RX_ID_MP = re.compile(r"\b\d{3,7}-\d{1,4}-(?:LE|LP|LR|LQ|CO|B2|L1|SE)\d{2}\b", re.I)


def _es_rut(texto, ini, fin):
    """True si la cifra es en realidad un RUT (por el dígito verificador o por la palabra previa)."""
    return bool(RX_DV_RUT.match(texto[fin:fin + 4]) or RX_ANTES_RUT.search(texto[max(0, ini - 24):ini]))


def _es_codigo(texto, ini, fin):
    """True si la cifra es un tramo de una secuencia punteada más larga (código de cuenta).
    'cuenta N°215.29.99.999.092.001.01.01' → el recorte '99.999.092.001' no es plata."""
    if ini > 0 and texto[ini - 1] in ".,":
        return True
    if re.match(r"^\.\d", texto[fin:fin + 2]):
        return True
    return False


def es_ajeno(codigo, texto):
    """True si el documento declara IDs de licitación y NINGUNO es el de esta carpeta.

    Conservador a propósito: un documento que no menciona ningún ID (la mayoría de los anexos)
    se considera propio. Sólo se descarta cuando el papel dice explícitamente de quién es y no
    es de acá."""
    ids = {m.group(0).upper() for m in RX_ID_MP.finditer(texto or "")}
    return bool(ids) and (codigo or "").upper() not in ids


def _valor(s):
    n = re.sub(r"\D", "", s or "")
    return int(n) if n else None


def candidatos(texto, origen=""):
    """Cifras plausibles de presupuesto con su contexto y un peso de confianza.

    El peso combina: qué tan específica es la palabra clave, si la cifra viene además escrita en
    palabras (la confirmación más fuerte), y si el signo $ está pegado."""
    t = texto or ""
    out = []
    for rx, peso_clave in _RX_CLAVES:
        for m in rx.finditer(t):
            ventana = t[m.start(): m.start() + 340]
            base = m.start()
            for mp in RX_PLATA.finditer(ventana):
                ini, fin = base + mp.start(), base + mp.end()
                if _es_rut(t, ini, fin) or _es_codigo(t, ini, fin):
                    continue
                v = _valor(mp.group(0))
                if v is None or not (MONTO_MIN <= v <= MONTO_MAX):
                    continue
                cola = t[fin: fin + 160]
                en_palabras = bool(RX_PALABRAS.search(cola))
                con_signo = "$" in t[max(0, ini - 4):ini]
                peso = peso_clave + (6 if en_palabras else 0) + (2 if con_signo else 0)
                out.append({
                    "valor": v, "clave": m.group(0).lower(), "peso": peso,
                    "en_palabras": en_palabras, "origen": origen,
                    "iva_incluido": _iva(ventana),
                    "fragmento": " ".join(t[max(0, ini - 130): fin + 170].split()),
                })
                break                       # la primera cifra tras la clave es la del techo
    out.sort(key=lambda x: -x["peso"])
    return out


def _iva(ventana):
    """True/False/None según lo que diga el texto alrededor de la cifra."""
    if RX_IVA_INC.search(ventana):
        return True
    if RX_IVA_MAS.search(ventana):
        return False
    return None


def _documentos(codigo):
    with db.conn() as c:
        filas = c.execute("SELECT nombre_archivo, ruta_local FROM documentos WHERE codigo=?",
                          (codigo,)).fetchall()
    return [(f["nombre_archivo"] or "", f["ruta_local"]) for f in filas
            if not (f["nombre_archivo"] or "").lower().startswith(("analisis_", "análisis_"))]


def del_pliego(codigo):
    """Lee los documentos de la licitación y devuelve el techo con su evidencia.

    Devuelve {monto, iva_incluido, fuente, confianza, n_documentos, alternativas, fragmento}
    o None si no encontró nada. `alternativas` importa: cuando el pliego trae más de una cifra
    (un decreto que aprueba $97M y un ábaco con una línea de $54M) hay que mirarlas, no promediarlas."""
    import bases
    todos, ajenos = [], []
    for nombre, ruta in _documentos(codigo):
        try:
            t = (bases.documento_a_texto(ruta) or {}).get("texto") or ""
        except Exception:                       # un anexo ilegible no invalida al resto
            continue
        if es_ajeno(codigo, t):                 # papel de OTRA licitación traspapelado en la carpeta
            ajenos.append(nombre)
            continue
        todos.extend(candidatos(t, origen=nombre))
    if not todos:
        return None

    # Acuerdo entre documentos: una cifra repetida en varios archivos distintos es la del pliego,
    # no un número suelto de un anexo.
    por_valor = {}
    for c in todos:
        d = por_valor.setdefault(c["valor"], {"peso": 0, "docs": set(), "mejor": c})
        d["peso"] += c["peso"]
        d["docs"].add(c["origen"])
        if c["peso"] > d["mejor"]["peso"]:
            d["mejor"] = c
    for d in por_valor.values():
        d["peso"] += 8 * (len(d["docs"]) - 1)   # +8 por cada documento adicional que la confirma

    orden = sorted(por_valor.items(), key=lambda kv: -kv[1]["peso"])
    valor, top = orden[0]
    mejor = top["mejor"]
    return {
        "monto": valor,
        "iva_incluido": mejor["iva_incluido"],
        "fuente": mejor["origen"],
        "clave": mejor["clave"],
        "confianza": "alta" if (mejor["en_palabras"] and len(top["docs"]) > 1)
                     else "media" if (mejor["en_palabras"] or len(top["docs"]) > 1) else "baja",
        "n_documentos": len(top["docs"]),
        "documentos_ajenos": ajenos,            # traspapelados: se leyeron y se descartaron
        "fragmento": mejor["fragmento"][:400],
        "alternativas": [{"valor": v, "peso": d["peso"], "docs": sorted(d["docs"])[:3]}
                         for v, d in orden[1:4]],
    }


def al_ingestar(codigos, solo_si_falta=True):
    """Completa `monto_estimado` en las licitaciones que lo tenían en null. Lo llama ingest_bases.

    Nunca pisa un monto que ya vino del API: el API es la fuente oficial y el pliego el respaldo.
    Nunca propaga excepciones."""
    escritos, sin_hallazgo = [], []
    try:
        schema_v3.migrate()
        with db.conn() as c:
            faltan = {r["codigo"] for r in c.execute(
                "SELECT codigo FROM licitaciones WHERE monto_estimado IS NULL OR monto_estimado <= 0")}
    except Exception:
        return {"escritos": [], "sin_hallazgo": [], "error": "no se pudo leer la BD"}

    for cod in (codigos or []):
        if solo_si_falta and cod not in faltan:
            continue
        try:
            r = del_pliego(cod)
        except Exception:
            continue
        if not r:
            sin_hallazgo.append(cod)
            continue
        try:
            with db.conn() as c:
                c.execute("UPDATE licitaciones SET monto_estimado=?, moneda=COALESCE(moneda,'CLP') "
                          "WHERE codigo=?", (r["monto"], cod))
                iva = ("IVA incluido" if r["iva_incluido"] else
                       "NETO (sin IVA)" if r["iva_incluido"] is False else "IVA sin determinar")
                db.log_evento(c, cod, "monto",
                              f"Monto leído del PLIEGO (el API lo dejaba en null): {r['monto']:,} — "
                              f"{iva}, confianza {r['confianza']}, vía '{r['clave']}' en {r['fuente']}."
                              .replace(",", "."))
            escritos.append({"codigo": cod, **{k: r[k] for k in
                                               ("monto", "iva_incluido", "confianza", "fuente")}})
        except Exception:
            continue
    return {"escritos": escritos, "sin_hallazgo": sin_hallazgo}


def faltantes():
    """Vigentes con bases descargadas y sin monto: las candidatas a completar."""
    schema_v3.migrate()
    with db.conn() as c:
        return [r["codigo"] for r in c.execute(
            "SELECT codigo FROM licitaciones WHERE vigente_oferta=1 AND docs_estado='descargado' "
            "AND (monto_estimado IS NULL OR monto_estimado <= 0)")]


if __name__ == "__main__":
    import sys, json
    args = sys.argv[1:]
    if args and args[0] == "--faltantes":
        print(json.dumps(faltantes(), indent=2, ensure_ascii=False))
    elif args and args[0] == "--completar":
        print(json.dumps(al_ingestar(faltantes()), indent=2, ensure_ascii=False, default=str))
    elif args:
        print(json.dumps(del_pliego(args[0]), indent=2, ensure_ascii=False, default=str))
    else:
        print(__doc__)
