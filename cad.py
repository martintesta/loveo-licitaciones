"""
cad.py — Lectura de planos DWG/DXF (extensión de Capa C para archivos CAD).

Convierte DWG -> DXF con ODA File Converter (local, gratuito, opendesign.com) y extrae con
ezdxf lo que sirve para cruzar contra las bases: textos/anotaciones, cotas (dimensiones reales
del plano), conteo de bloques insertados (equipos/símbolos repetidos) y capas.

  convertir_a_dxf(ruta_dwg)            -> ruta al .dxf (cachea al lado del .dwg; no reconvierte
                                           si ya existe y es más nuevo que el .dwg)
  extraer_dxf(ruta)                    -> dict {texto, dimensiones, bloques, capas, n_entidades}
  texto_para_analisis(ruta, max_chars) -> mismo shape que bases.texto_para_analisis(), para
                                           enchufar directo en el loop de documentos de capa_c.py

Requiere ODA File Converter instalado (gratis, sin licencia). Si no está, RuntimeError con el
link de descarga — no rompe el resto del análisis (capa_c.py lo captura por documento).
"""
import os
import glob
import shutil
import subprocess
import tempfile
from pathlib import Path
from collections import Counter

EXTENSIONES_CAD = (".dwg", ".dxf")

ODA_LINK = "https://www.opendesign.com/guestfiles/oda_file_converter"


def _encontrar_oda():
    for base in (r"C:\Program Files\ODA", r"C:\Program Files (x86)\ODA"):
        for hit in sorted(glob.glob(os.path.join(base, "ODAFileConverter*", "ODAFileConverter.exe")),
                           reverse=True):  # la versión más nueva primero, por si hay varias
            if os.path.isfile(hit):
                return hit
    return None


def convertir_a_dxf(ruta_dwg, forzar=False, timeout=180):
    """Convierte un .dwg a .dxf con ODA File Converter (ACAD2018, sin auditoría de reparación).
    Cachea al lado del .dwg: si el .dxf ya existe y es más nuevo, no reconvierte."""
    ruta_dwg = Path(ruta_dwg)
    if ruta_dwg.suffix.lower() == ".dxf":
        return str(ruta_dwg)
    dxf_out = ruta_dwg.with_suffix(".dxf")
    if dxf_out.exists() and not forzar and dxf_out.stat().st_mtime >= ruta_dwg.stat().st_mtime:
        return str(dxf_out)
    exe = _encontrar_oda()
    if not exe:
        raise RuntimeError(f"ODA File Converter no está instalado. Descargalo gratis de {ODA_LINK} "
                            f"e instalalo (necesita permisos de administrador), después repetí el análisis.")
    with tempfile.TemporaryDirectory() as tin, tempfile.TemporaryDirectory() as tout:
        shutil.copy(ruta_dwg, tin)
        proc = subprocess.run([exe, tin, tout, "ACAD2018", "DXF", "0", "1"],
                               capture_output=True, timeout=timeout)
        salida = list(Path(tout).glob("*.dxf"))
        if not salida:
            raise RuntimeError(f"ODA File Converter no generó salida para {ruta_dwg.name} "
                                f"(exit={proc.returncode}). Archivo corrupto, encriptado, o "
                                f"versión de DWG no soportada.")
        shutil.copy(salida[0], dxf_out)
    return str(dxf_out)


def extraer_dxf(ruta):
    """Extrae del DXF (convierte primero si viene un .dwg) lo que sirve para cruzar contra las
    bases. NO intenta interpretar el dibujo geométricamente (líneas/arcos) — eso no dice nada
    sin un motor de render; lo que sí es información real y verificable son las ANOTACIONES
    (texto puesto por quien dibujó) y las COTAS (dimensiones que el plano declara explícitamente).
    Devuelve dict: {texto: [str,...] (dedup), dimensiones: [{layer, capa, valor, texto}],
    bloques: {nombre: cantidad}, capas: [str,...], n_entidades: int, archivo_dwg, archivo_dxf}."""
    import ezdxf
    ruta_dxf = convertir_a_dxf(ruta) if str(ruta).lower().endswith(".dwg") else str(ruta)
    doc = ezdxf.readfile(ruta_dxf)
    msp = doc.modelspace()

    textos = set()
    dimensiones = []
    bloques = Counter()
    n_entidades = 0

    for e in msp:
        n_entidades += 1
        tipo = e.dxftype()
        if tipo in ("TEXT", "ATTRIB", "ATTDEF"):
            t = (e.dxf.text or "").strip()
            if t:
                textos.add(t)
        elif tipo == "MTEXT":
            t = (e.text or e.plain_text() or "").strip()
            if t:
                textos.add(t)
        elif tipo == "DIMENSION":
            try:
                valor = e.get_measurement()
            except Exception:
                valor = None
            texto_dim = (e.dxf.text or "").strip() if e.dxf.hasattr("text") else ""
            dimensiones.append({
                "capa": e.dxf.layer,
                "valor": round(valor, 3) if isinstance(valor, (int, float)) else None,
                "texto": texto_dim or None,
            })
        elif tipo == "INSERT":
            bloques[e.dxf.name] += 1

    capas = sorted(l.dxf.name for l in doc.layers)
    return {
        "archivo_dwg": str(ruta) if str(ruta).lower().endswith(".dwg") else None,
        "archivo_dxf": ruta_dxf,
        "texto": sorted(textos),
        "dimensiones": dimensiones,
        "bloques": dict(bloques.most_common()),
        "capas": capas,
        "n_entidades": n_entidades,
    }


def texto_para_analisis(ruta, max_chars=12000):
    """Mismo shape que bases.texto_para_analisis() — se enchufa directo en el loop de documentos
    de capa_c.py sin tocar su lógica, solo despachando por extensión. Arma un texto legible con
    las anotaciones y cotas del plano, para que la IA lo cruce contra lo que dicen las bases
    (ej.: '¿el plano dice 6,00 x 2,40 m, coincide con lo que pide el EETT?')."""
    ex = extraer_dxf(ruta)
    partes = [f"### PLANO CAD: {Path(ruta).name}",
              f"{ex['n_entidades']} entidades, {len(ex['capas'])} capas, "
              f"{sum(ex['bloques'].values())} bloques insertados ({len(ex['bloques'])} tipos distintos)."]

    if ex["dimensiones"]:
        cotas = [f"{d['valor']} m" + (f" ({d['texto']})" if d["texto"] else "")
                 for d in ex["dimensiones"] if d["valor"] is not None]
        if cotas:
            partes.append("COTAS DEL PLANO (dimensiones reales acotadas): " + ", ".join(cotas[:80]))

    if ex["bloques"]:
        top_bloques = ", ".join(f"{n}×{c}" for n, c in list(ex["bloques"].items())[:40])
        partes.append(f"BLOQUES INSERTADOS (posibles equipos/símbolos repetidos): {top_bloques}")

    if ex["texto"]:
        partes.append("TEXTOS/ANOTACIONES DEL PLANO:\n" + "\n".join(f"- {t}" for t in ex["texto"][:200]))

    texto = "\n\n".join(partes)
    return {"texto": texto[:max_chars], "n_paginas": None, "ocr_paginas": [],
            "secciones_halladas": ["plano_cad"], "n_entidades": ex["n_entidades"],
            "n_dimensiones": len(ex["dimensiones"]), "n_bloques": len(ex["bloques"])}


if __name__ == "__main__":
    import sys, json
    ruta = sys.argv[1] if len(sys.argv) > 1 else None
    if not ruta:
        print("Uso: python cad.py <ruta.dwg|ruta.dxf>")
        raise SystemExit(1)
    ex = extraer_dxf(ruta)
    print(f"Entidades: {ex['n_entidades']} | Capas: {len(ex['capas'])} | "
          f"Bloques: {sum(ex['bloques'].values())} ({len(ex['bloques'])} tipos) | "
          f"Cotas: {len(ex['dimensiones'])} | Textos únicos: {len(ex['texto'])}")
    print("\n--- muestra de texto (primeros 20) ---")
    for t in ex["texto"][:20]:
        print(" -", t)
    print("\n--- top 15 bloques ---")
    for n, c in list(ex["bloques"].items())[:15]:
        print(f"  {n}: {c}")
