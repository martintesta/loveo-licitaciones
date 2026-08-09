"""
ingest_bases.py — Ingesta manual de bases (workaround del reCAPTCHA de la Capa B).

Mercado Público protege los adjuntos con reCAPTCHA → no se pueden bajar solos. Un humano las
descarga y las deja en una carpeta madre con UNA SUBCARPETA POR CÓDIGO. Esto escanea esa carpeta,
matchea cada subcarpeta con una licitación de la base y registra sus archivos en `documentos` → la
Capa C los lee y puntúa. Dos lectores de la MISMA verdad, uno por runtime:

  - desde_local(carpeta): la app corre en la misma máquina → registra las bases EN EL LUGAR (sin
    copiar), leyendo la ruta directa. Es el camino primario en tu notebook / el worker.
  - desde_drive(link): puente a la nube → baja las bases a storage/<codigo> vía la conexión OAuth de
    drive.py (para cuando la app está hosteada u otro usuario las necesita).

  desde_local(carpeta) -> {ok, subcarpetas, matched, registrados, huerfanos[], detalle[]}
  desde_drive(link)     -> {ok, subcarpetas, matched, bajados, detalle[]}

  python ingest_bases.py --local                 # usa LOVEO_BASES_LOCAL de .env
  python ingest_bases.py --local "D:\\Loveo\\Bases"
  python ingest_bases.py "<link carpeta madre de Drive>"   # o LOVEO_DRIVE_BASES en .env
"""
import os
import pathlib
import hashlib

import db
import schema_v3


def _confinado(raiz_res, hijo):
    """True si `hijo` (ya resuelto) cae dentro de `raiz_res` (defensa ante symlinks que escapan).
    `is_relative_to` (3.9+) evita los bordes de casing/trailing-slash de commonpath en Windows."""
    return hijo == raiz_res or hijo.is_relative_to(raiz_res)


def _registrar_local(cod, path):
    """Registra un archivo local EN EL LUGAR (sin copiar). Idempotente por (codigo, ruta_local): si
    ya está registrado no lo re-lee (evita re-hashear PDFs en cada corrida). True si registró algo."""
    ruta = str(path)
    with db.conn() as c:
        if c.execute("SELECT 1 FROM documentos WHERE codigo=? AND ruta_local=?", (cod, ruta)).fetchone():
            return False
    _registrar(cod, path.name, path, path.read_bytes(), fuente="local")
    return True


def desde_local(carpeta=None):
    """Escanea una carpeta madre LOCAL (subcarpeta por código) y registra las bases en el lugar.
    Matchea el nombre de subcarpeta con un código de la base; reporta las que no matchean (huérfanas).
    `carpeta` por arg o LOVEO_BASES_LOCAL en .env."""
    carpeta = carpeta or os.environ.get("LOVEO_BASES_LOCAL", "")
    if not carpeta:
        return {"ok": False, "error": "Falta la carpeta madre (arg o LOVEO_BASES_LOCAL en .env)."}
    raiz = pathlib.Path(carpeta).expanduser()
    if not raiz.is_dir():
        return {"ok": False, "error": f"No existe la carpeta: {raiz}"}
    schema_v3.migrate()

    raiz_res = raiz.resolve()
    with db.conn() as c:
        codigos = {r["codigo"] for r in c.execute("SELECT codigo FROM licitaciones").fetchall()}

    subs = [s for s in sorted(raiz.iterdir()) if s.is_dir()]
    matched, registrados, huerfanos, detalle = 0, 0, [], []
    con_nuevos, matcheados = [], []
    for sub in subs:
        cod = sub.name.strip()
        if cod not in codigos:            # subcarpeta que no matchea ninguna licitación → huérfana
            huerfanos.append(sub.name)
            continue
        matched += 1
        matcheados.append(cod)
        n = 0
        for f in sorted(sub.iterdir()):
            if not f.is_file():
                continue
            real = f.resolve()
            if not _confinado(raiz_res, real):     # symlink que escapa de la carpeta madre → skip
                continue
            if _registrar_local(cod, real):
                n += 1
                registrados += 1
        if n:
            con_nuevos.append(cod)
        detalle.append({"codigo": cod, "archivos": n})
    return {"ok": True, "subcarpetas": len(subs), "matched": matched, "registrados": registrados,
            "huerfanos": huerfanos, "detalle": detalle,
            "visitas": _detectar_visitas(con_nuevos, matcheados)}


def _detectar_visitas(con_nuevos, matcheados):
    """Corre la detección de visita a terreno sobre lo recién ingestado.

    Va acá y no en la Capa C porque ESTE es el primer momento en que el dato existe: la visita
    está escrita en el pliego (el `Fechas.FechaVisitaTerreno` del API viene null siempre) y suele
    convocarse a los pocos días de publicada. Detectarla al analizar es detectarla tarde.

    Aislada en su propia función y con try/except porque la ingesta de bases no puede fallar por
    un pliego escaneado que rompa el OCR."""
    try:
        import visitas
        return visitas.al_ingestar(con_nuevos, matcheados)
    except Exception as e:
        return {"error": str(e)[:200]}


def _registrar(cod, nombre, path, contenido, fuente="drive"):
    with db.conn() as c:
        c.execute("INSERT OR IGNORE INTO documentos "
                  "(codigo, nombre_archivo, ruta_local, tipo, bytes, sha256, fuente, descargado_at) "
                  "VALUES (?,?,?,?,?,?,?,?)",
                  (cod, nombre, str(path), path.suffix.lstrip("."), len(contenido),
                   hashlib.sha256(contenido).hexdigest(), fuente, db._now()))
        # deja la lic lista para la Capa C (sin pisar un estado ya 'descargado')
        c.execute("UPDATE licitaciones SET docs_estado='descargado' "
                  "WHERE codigo=? AND (docs_estado IS NULL OR docs_estado != 'descargado')", (cod,))


def desde_drive(link=None, drv=None):
    """Escanea la carpeta madre de Drive y baja las bases de las subcarpetas que matcheen un código.
    `drv` inyectable para tests (por defecto usa el módulo drive real)."""
    link = link or os.environ.get("LOVEO_DRIVE_BASES", "")
    if not link:
        return {"ok": False, "error": "Falta el link de la carpeta madre (arg o LOVEO_DRIVE_BASES en .env)."}
    if drv is None:
        import drive as drv
    if not drv.disponible():
        return {"ok": False, "error": "Drive no conectado. Corré 'python drive.py auth' (ver SETUP_DRIVE.md)."}
    schema_v3.migrate()

    kind, gid = drv.parse_link(link)
    if kind != "folder":
        return {"ok": False, "error": "El link no es de una carpeta de Drive."}
    svc = drv._service()
    with db.conn() as c:
        codigos = {r["codigo"] for r in c.execute("SELECT codigo FROM licitaciones").fetchall()}

    subs = drv.list_subfolders(gid, svc)
    matched, bajados, fallidos, detalle = 0, 0, 0, []
    con_nuevos, matcheados = [], []
    for sub in subs:
        cod = (sub["name"] or "").strip()
        if cod not in codigos:                 # subcarpeta que no matchea ninguna licitación → ignorar
            continue
        matched += 1
        matcheados.append(cod)
        n = 0
        dest = (db.STORAGE_DIR / cod).resolve()
        for f in drv.list_folder(sub["id"], svc):
            if f.get("mimeType") == drv.FOLDER_MIME:
                continue                        # no recursivo dentro de la subcarpeta del código
            dest.mkdir(parents=True, exist_ok=True)
            destino = db.safe_child(dest, f["name"])   # basename + confinado (anti path traversal)
            if not destino:
                continue
            try:
                ruta, _, _ = drv.download_file(f["id"], str(destino), svc)
                real = pathlib.Path(ruta)          # ruta REAL escrita (Google-native le agrega ext)
                _registrar(cod, real.name, real, real.read_bytes())
                n += 1
                bajados += 1
            except Exception:                      # un archivo que falla no frena el resto
                fallidos += 1
        if n:
            con_nuevos.append(cod)
        detalle.append({"codigo": cod, "archivos": n})
    return {"ok": True, "subcarpetas": len(subs), "matched": matched, "bajados": bajados,
            "fallidos": fallidos, "detalle": detalle,
            "visitas": _detectar_visitas(con_nuevos, matcheados)}


if __name__ == "__main__":
    import sys
    import json
    args = sys.argv[1:]
    if args and args[0] == "--local":                 # fuente LOCAL (app en la misma máquina)
        carpeta = args[1] if len(args) > 1 else None
        print(json.dumps(desde_local(carpeta), indent=2, ensure_ascii=False))
    else:                                             # fuente DRIVE (puente a la nube)
        link = args[0] if args else None
        print(json.dumps(desde_drive(link), indent=2, ensure_ascii=False))
