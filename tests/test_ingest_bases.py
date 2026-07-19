"""
test_ingest_bases.py — Sensor de la ingesta de bases desde Drive (workaround del reCAPTCHA).

desde_drive escanea una carpeta madre, matchea subcarpetas por código con licitaciones de la base,
baja sus archivos y los registra en documentos dejando docs_estado='descargado' (para la Capa C).
Drive INYECTADO (fake) → no toca la red ni credenciales. SQLite temporal.

  python -m pytest tests/test_ingest_bases.py -q
"""
import pathlib

import db
import ingest_bases
import schema_v3


class _FakeDrive:
    FOLDER_MIME = "application/vnd.google-apps.folder"

    def disponible(self):
        return True

    def parse_link(self, link):
        return ("folder", "MOTHER")

    def _service(self):
        return None

    def list_subfolders(self, gid, svc):
        return [{"id": "s1", "name": "3287-19-LE26"},   # matchea una lic
                {"id": "s2", "name": "9999-99-XX99"}]   # NO matchea ninguna → ignorar

    def list_folder(self, fid, svc):
        return {"s1": [{"id": "f1", "name": "bases.pdf", "mimeType": "application/pdf"},
                       {"id": "f2", "name": "anexo.pdf", "mimeType": "application/pdf"}],
                "s2": [{"id": "f9", "name": "otra.pdf", "mimeType": "application/pdf"}]}[fid]

    def download_file(self, fid, dest, svc):
        p = pathlib.Path(dest)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"PDF-" + fid.encode())
        return str(p), p.name, "application/pdf"


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "STORAGE_DIR", tmp_path / "storage")
    db.init_db()
    schema_v3.migrate()
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "3287-19-LE26", "nombre": "Container marítimos"})


def test_ingesta_solo_las_subcarpetas_que_matchean(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = ingest_bases.desde_drive("https://drive.google.com/drive/folders/MOTHER", drv=_FakeDrive())
    assert r["ok"] and r["subcarpetas"] == 2 and r["matched"] == 1 and r["bajados"] == 2
    # los archivos quedaron en storage/<codigo> y registrados en documentos
    with db.conn() as c:
        docs = c.execute("SELECT nombre_archivo, fuente FROM documentos WHERE codigo=?",
                         ("3287-19-LE26",)).fetchall()
        est = c.execute("SELECT docs_estado FROM licitaciones WHERE codigo='3287-19-LE26'").fetchone()
    assert {d["nombre_archivo"] for d in docs} == {"bases.pdf", "anexo.pdf"}
    assert all(d["fuente"] == "drive" for d in docs)
    assert est["docs_estado"] == "descargado"           # lista para la Capa C
    # la subcarpeta que no matchea NO se bajó
    assert not (tmp_path / "storage" / "9999-99-XX99").exists()


def test_reingesta_no_duplica(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    ingest_bases.desde_drive("x/folders/MOTHER", drv=_FakeDrive())
    ingest_bases.desde_drive("x/folders/MOTHER", drv=_FakeDrive())   # otra vez: dedup por (codigo, sha256)
    with db.conn() as c:
        n = c.execute("SELECT COUNT(*) n FROM documentos WHERE codigo='3287-19-LE26'").fetchone()["n"]
    assert n == 2


def test_sin_link_devuelve_error(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.delenv("LOVEO_DRIVE_BASES", raising=False)
    assert ingest_bases.desde_drive(None, drv=_FakeDrive())["ok"] is False


def test_link_que_no_es_carpeta(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    class _F(_FakeDrive):
        def parse_link(self, link):
            return ("file", "X")

    assert ingest_bases.desde_drive("x/file/X", drv=_F())["ok"] is False


def test_usa_el_path_real_de_download_google_native(tmp_path, monkeypatch):
    """Google Sheet/Doc: download_file guarda con extensión appendeada; el ingest debe registrar
    y leer ESE path (antes leía el pre-extensión → FileNotFoundError → archivo huérfano)."""
    _setup(tmp_path, monkeypatch)

    class _GoogleDrive(_FakeDrive):
        def list_subfolders(self, gid, svc):
            return [{"id": "s1", "name": "3287-19-LE26"}]

        def list_folder(self, fid, svc):
            return [{"id": "f1", "name": "Presupuesto",
                     "mimeType": "application/vnd.google-apps.spreadsheet"}]

        def download_file(self, fid, dest, svc):
            real = pathlib.Path(str(dest) + ".xlsx")   # el export le agrega la extensión
            real.parent.mkdir(parents=True, exist_ok=True)
            real.write_bytes(b"XLSX")
            return str(real), real.name, "application/vnd.openxmlformats"

    r = ingest_bases.desde_drive("x/folders/M", drv=_GoogleDrive())
    assert r["ok"] and r["bajados"] == 1 and r.get("fallidos", 0) == 0
    with db.conn() as c:
        d = c.execute("SELECT nombre_archivo, ruta_local FROM documentos WHERE codigo='3287-19-LE26'").fetchone()
    assert d["nombre_archivo"] == "Presupuesto.xlsx" and d["ruta_local"].endswith("Presupuesto.xlsx")


def test_safe_child_bloquea_traversal(tmp_path):
    base = tmp_path / "storage"
    base.mkdir()
    assert db.safe_child(base, "bases.pdf") == (base / "bases.pdf").resolve()
    assert db.safe_child(base, "../evil.txt") == (base / "evil.txt").resolve()    # basename → confinado
    assert db.safe_child(base, "..\\..\\evil") == (base / "evil").resolve()       # backslash cross-OS
    assert db.safe_child(base, "") is None
    assert db.safe_child(base, "..") is None
