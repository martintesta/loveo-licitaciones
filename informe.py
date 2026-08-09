"""
informe.py — Genera el ANÁLISIS INTEGRAL de una licitación en .xlsx y lo deja donde corresponde.

Orquesta tres piezas y no hace nada más:
    digest.py         → lee TODOS los documentos de las bases (con OCR) y los reduce a un digest
    analisis.py       → arma los datos: determinista de la base + UNA llamada a Claude
    excel_analisis.py → los baja a un Excel de 8-9 hojas con FÓRMULAS encadenadas

Hojas: Resumen · Objeto y Alineación · Cubicación · Compras · Financiero · Riesgos · RACI ·
       Estrategia Ganar (si hay matriz de evaluación) · Competencia (si hay censo).

EL PUNTO DEL EXCEL: nada derivado va congelado. Editar Cantidad o Precio unitario en «Cubicación»
recalcula costo base → sobrecosto → financiamiento → escenarios de oferta → P&L → KPIs del Resumen.

GUARDADO: el archivo SIEMPRE queda en la carpeta de bases de la licitación (la misma donde están
los PDFs), además de devolverse como bytes para la descarga del tablero. Si esa carpeta no existe
todavía, se crea; si no hay carpeta madre configurada, cae a storage/<codigo>.

  generar(codigo)      -> {ok, xlsx, ruta, hojas, con_ia} | {ok: False, error}
  generar_xlsx(codigo) -> bytes | {"error": ...}     (forma corta, la que usa el tablero)
"""
import datetime
import io
import os
import pathlib
import sys

import analisis
import db
import excel_analisis


def carpeta_destino(codigo):
    """Dónde vive esta licitación. En orden de preferencia:
      1) la carpeta real donde están sus documentos registrados (la de verdad, la que abre Martín),
      2) LOVEO_BASES_LOCAL/<codigo> (carpeta madre configurada, aunque todavía esté vacía),
      3) storage/<codigo> (fallback: app hosteada, sin carpeta local).
    Devuelve un Path ya creado."""
    with db.conn() as c:
        row = c.execute("SELECT ruta_local FROM documentos WHERE codigo=? AND ruta_local IS NOT NULL "
                        "ORDER BY id LIMIT 1", (codigo,)).fetchone()
    if row and row[0]:
        p = pathlib.Path(str(row[0])).parent
        if p.is_dir():
            return p
    madre = os.environ.get("LOVEO_BASES_LOCAL", "").strip()
    if madre:
        raiz = pathlib.Path(madre).expanduser()
        if raiz.is_dir():
            destino = db.safe_child(raiz, codigo)       # confinado a la carpeta madre
            if destino:
                destino.mkdir(parents=True, exist_ok=True)
                return destino
    destino = db.STORAGE_DIR / codigo
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def nombre_archivo(codigo, fecha=None):
    fecha = fecha or datetime.date.today()
    return f"Analisis_{str(codigo).replace('/', '-')}_{fecha.isoformat()}.xlsx"


def generar(codigo, enriquecer=None, hoy=None):
    """Análisis integral completo. Devuelve los bytes y la ruta donde quedó guardado.
    `enriquecer` se pasa a analisis.datos() (inyectable para tests sin red)."""
    hoy = hoy or datetime.date.today()
    D = analisis.datos(codigo, enriquecer=enriquecer, hoy=hoy)
    if D.get("error"):
        return {"ok": False, "error": D["error"]}

    wb = excel_analisis.construir(D)
    buf = io.BytesIO()
    wb.save(buf)
    xlsx = buf.getvalue()

    ruta, error_guardado = None, None
    try:
        destino = carpeta_destino(codigo) / nombre_archivo(codigo, hoy)
        destino.write_bytes(xlsx)
        ruta = str(destino)
    except OSError as e:      # disco lleno, permisos, OneDrive desconectado: la descarga igual sirve
        error_guardado = f"No se pudo guardar en la carpeta de bases ({e.__class__.__name__}: {e})."

    with db.conn() as c:
        db.log_evento(c, codigo, "informe",
                      f"Análisis integral generado ({len(wb.sheetnames)} hojas"
                      f"{', con IA' if D.get('_ia') else ', sin IA'})."
                      + (f" Guardado en {ruta}." if ruta else f" {error_guardado}"))

    return {"ok": True, "xlsx": xlsx, "ruta": ruta, "hojas": list(wb.sheetnames),
            "con_ia": bool(D.get("_ia")), "aviso": error_guardado,
            "info_faltante": D.get("info_faltante") or []}


def generar_xlsx(codigo, enriquecer=None):
    """Forma corta: bytes del .xlsx, o {"error": ...} si el código no existe.
    Guarda igual en la carpeta de bases (es el requisito, no un efecto secundario opcional)."""
    r = generar(codigo, enriquecer=enriquecer)
    return r["xlsx"] if r.get("ok") else {"error": r.get("error", "No se pudo generar el informe.")}


def _p(txt):
    """La consola de Windows es cp1252 y revienta con '≥', '·' o cualquier tilde rara: un análisis
    que se generó bien no puede morir en el print del resumen."""
    codec = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(str(txt).encode(codec, errors="replace").decode(codec))


if __name__ == "__main__":
    r = generar(sys.argv[1])
    if not r.get("ok"):
        _p(f"ERROR: {r['error']}")
        raise SystemExit(1)
    _p(f"OK: {len(r['xlsx'])} bytes - hojas: {', '.join(r['hojas'])}")
    _p(f"IA: {'si' if r['con_ia'] else 'no'} - guardado en: {r['ruta'] or '(no se pudo guardar)'}")
    for x in r["info_faltante"]:
        _p(f"  falta: {x}")
