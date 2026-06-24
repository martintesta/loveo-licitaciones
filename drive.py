"""
drive.py — Acceso a Google Drive: pegás el link de una CARPETA y el sistema lista y baja
todos los archivos de adentro (para después leerlos con la Capa C).

Credenciales (una sola vez, ver SETUP_DRIVE.md). Autodetecta, en este orden:
  1) service_account.json  → cuenta de servicio (compartí la carpeta con el email del SA).
  2) credentials.json + token.json → OAuth de tu cuenta (consentís una vez en el navegador).

CLI:
  python drive.py auth                  # corre el consentimiento OAuth (genera token.json)
  python drive.py ls  "<link carpeta>"  # lista los archivos de la carpeta
  python drive.py get "<link>" <dir>    # baja la carpeta/archivo a <dir>

Todo es de solo lectura (scope drive.readonly). Nada de credenciales se sube (van en .gitignore).
"""
import os
import re
import sys
import io
from pathlib import Path

BASE = Path(__file__).parent
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
SA_FILE = BASE / "service_account.json"
OAUTH_CRED = BASE / "credentials.json"
TOKEN = BASE / "token.json"
GOOGLE_DOC_EXPORT = {  # Google Docs nativos -> exportar
    "application/vnd.google-apps.document": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.spreadsheet": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
}


def parse_link(link):
    """Devuelve ('folder'|'file', id) a partir de un link de Drive (o un id pelado)."""
    link = (link or "").strip()
    m = re.search(r"/folders/([A-Za-z0-9_-]+)", link)
    if m:
        return "folder", m.group(1)
    m = re.search(r"/file/d/([A-Za-z0-9_-]+)", link)
    if m:
        return "file", m.group(1)
    m = re.search(r"[?&]id=([A-Za-z0-9_-]+)", link)
    if m:
        return "file", m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{20,}", link):
        return "file", link
    return None, None


def disponible():
    """¿Hay credenciales para operar?"""
    return SA_FILE.exists() or TOKEN.exists()


def _service():
    from googleapiclient.discovery import build
    if SA_FILE.exists():
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(str(SA_FILE), scopes=SCOPES)
    elif TOKEN.exists():
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN.write_text(creds.to_json(), encoding="utf-8")
    else:
        raise RuntimeError("Sin credenciales de Drive. Corré 'python drive.py auth' o poné service_account.json. Ver SETUP_DRIVE.md")
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def auth():
    from google_auth_oauthlib.flow import InstalledAppFlow
    if not OAUTH_CRED.exists():
        raise RuntimeError("Falta credentials.json (OAuth Desktop). Ver SETUP_DRIVE.md")
    flow = InstalledAppFlow.from_client_secrets_file(str(OAUTH_CRED), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return "token.json generado"


def list_folder(folder_id, svc=None):
    """Lista archivos (no subcarpetas) de una carpeta."""
    svc = svc or _service()
    out, page = [], None
    q = f"'{folder_id}' in parents and trashed=false"
    while True:
        resp = svc.files().list(
            q=q, fields="nextPageToken, files(id,name,mimeType,size,modifiedTime)",
            pageSize=200, pageToken=page, orderBy="name",
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        out += resp.get("files", [])
        page = resp.get("nextPageToken")
        if not page:
            break
    return out


def download_file(file_id, dest_path, svc=None):
    from googleapiclient.http import MediaIoBaseDownload
    svc = svc or _service()
    meta = svc.files().get(fileId=file_id, fields="name,mimeType", supportsAllDrives=True).execute()
    name, mime = meta["name"], meta["mimeType"]
    if mime in GOOGLE_DOC_EXPORT:
        export_mime, ext = GOOGLE_DOC_EXPORT[mime]
        req = svc.files().export_media(fileId=file_id, mimeType=export_mime)
        if not str(dest_path).lower().endswith(ext):
            dest_path = str(dest_path) + ext
    else:
        req = svc.files().get_media(fileId=file_id, supportsAllDrives=True)
    Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
    buf = io.FileIO(str(dest_path), "wb")
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    buf.close()
    return str(dest_path), name, mime


def sync_link(link, dest_dir):
    """Baja todos los archivos de una carpeta (o un archivo) a dest_dir. Devuelve lista de dicts."""
    kind, gid = parse_link(link)
    if not gid:
        raise ValueError("Link de Drive no reconocido")
    os.makedirs(dest_dir, exist_ok=True)
    svc = _service()
    results = []
    if kind == "folder":
        for f in list_folder(gid, svc):
            if f["mimeType"] == "application/vnd.google-apps.folder":
                continue  # subcarpetas: por ahora no recursivo
            path, name, mime = download_file(f["id"], os.path.join(dest_dir, f["name"]), svc)
            results.append({"id": f["id"], "name": name, "path": path, "mime": mime})
    else:
        path, name, mime = download_file(gid, os.path.join(dest_dir, "drive_file"), svc)
        results.append({"id": gid, "name": name, "path": path, "mime": mime})
    return results


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)
    cmd = args[0]
    if cmd == "auth":
        print(auth())
    elif cmd == "ls" and len(args) > 1:
        kind, gid = parse_link(args[1])
        print(f"tipo={kind} id={gid}")
        if kind == "folder":
            for f in list_folder(gid):
                print(f"  - {f['name']}  [{f['mimeType']}]  {f.get('size','')}")
        else:
            print("  (es un archivo, no una carpeta)")
    elif cmd == "get" and len(args) > 2:
        for r in sync_link(args[1], args[2]):
            print(f"  bajado: {r['name']} -> {r['path']}")
    else:
        print("Uso: python drive.py [auth | ls <link> | get <link> <dir>]")
