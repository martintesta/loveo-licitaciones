"""
ingest_bases.py — Ingesta manual de bases desde Drive (workaround del reCAPTCHA de la Capa B).

Mercado Público protege los adjuntos con reCAPTCHA → no se pueden bajar solos. Un humano las
descarga y las deja en una carpeta madre de Drive, con UNA SUBCARPETA POR CÓDIGO. Esto escanea esa
carpeta, matchea cada subcarpeta con una licitación de la base, baja sus archivos a storage/<codigo>
y los registra en `documentos` → la Capa C los lee y puntúa. Reusa la conexión OAuth de drive.py
(actúa como tu cuenta: no hace falta compartir nada).

  desde_drive(link) -> {ok, subcarpetas, matched, bajados, detalle[]}

  python ingest_bases.py "<link carpeta madre de Drive>"
  # o poné LOVEO_DRIVE_BASES=<link> en .env y corré:  python ingest_bases.py
"""
import os
import pathlib
import hashlib

import db
import schema_v3


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
    for sub in subs:
        cod = (sub["name"] or "").strip()
        if cod not in codigos:                 # subcarpeta que no matchea ninguna licitación → ignorar
            continue
        matched += 1
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
        detalle.append({"codigo": cod, "archivos": n})
    return {"ok": True, "subcarpetas": len(subs), "matched": matched, "bajados": bajados,
            "fallidos": fallidos, "detalle": detalle}


if __name__ == "__main__":
    import sys
    import json
    link = sys.argv[1] if len(sys.argv) > 1 else None
    print(json.dumps(desde_drive(link), indent=2, ensure_ascii=False))
