"""
test_download.py — Sensor de la persistencia de la Capa B (download._guardar).

La descarga real es Playwright (no testeable sin IP chilena), pero el guardado a disco + el
registro en `documentos` con dedup por (codigo, sha256) es lógica pura. Contra SQLite temporal y
un STORAGE_DIR temporal (no toca ni Neon ni el storage real).

  python -m pytest tests/test_download.py -q
"""
import hashlib

import db
import download


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "STORAGE_DIR", tmp_path / "storage")
    db.init_db()
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "C1", "nombre": "x"})   # FK de documentos


def _docs(codigo):
    with db.conn() as c:
        return c.execute("SELECT nombre_archivo, ruta_local, bytes, sha256 FROM documentos "
                         "WHERE codigo=?", (codigo,)).fetchall()


def test_guardar_escribe_archivo_y_registra(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    sha = download._guardar("C1", "bases.pdf", b"contenido de prueba")
    assert sha == hashlib.sha256(b"contenido de prueba").hexdigest()
    destino = tmp_path / "storage" / "C1" / "bases.pdf"
    assert destino.read_bytes() == b"contenido de prueba"   # archivo en storage/<codigo>/
    filas = _docs("C1")
    assert len(filas) == 1
    assert filas[0]["nombre_archivo"] == "bases.pdf"
    assert filas[0]["bytes"] == len(b"contenido de prueba")
    assert filas[0]["sha256"] == sha


def test_guardar_dedup_por_codigo_y_sha(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    download._guardar("C1", "bases.pdf", b"mismo")
    download._guardar("C1", "bases.pdf", b"mismo")   # mismo (codigo, sha) → no duplica ni rompe
    assert len(_docs("C1")) == 1


def test_guardar_contenido_distinto_es_otra_fila(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    download._guardar("C1", "bases.pdf", b"v1")
    download._guardar("C1", "anexo.pdf", b"v2")      # otro sha → segunda fila
    assert len(_docs("C1")) == 2


def test_detecta_las_variantes_del_muro_antibot():
    # variante clásica y la de "Acceso denegado"/robot.png que devuelve ViewAttachment (vista en vivo)
    assert download._html_muro("<p>Detectamos ACTIVIDAD ANORMAL en su conexión</p>") is True
    assert download._html_muro('<img src="../images/robot.png" alt="Acceso denegado">') is True
    assert download._html_muro("<html>Acceso Denegado</html>") is True
    assert download._html_muro("<table id='grilla'><tr><td>bases.pdf</td></tr></table>") is False
    assert download._html_muro("") is False
