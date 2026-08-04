"""
test_capa_c.py — Integración de la Capa C con el cliente Anthropic mockeado.

No llama a la API ni lee PDFs: mockea bases.texto_para_analisis y capa_c._client, y verifica
el conteo dry, el parseo de la respuesta a JSON, el camino de parse_error y el de "sin docs".

  python -m pytest tests/test_capa_c.py -q
"""
import bases
import capa_c
import db


def test_estimar_tokens():
    assert capa_c._estimar_tokens("a" * 400) == 100  # ~4 chars/token


def test_analizar_sin_docs_devuelve_error(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    r = capa_c.analizar_bases(codigo="NO-DOCS")
    assert r.get("error")


def _mock_texto(monkeypatch):
    monkeypatch.setattr(bases, "texto_para_analisis",
                        lambda ruta, max_chars=12000: {"texto": "PRESUPUESTO 50M, plazo 60 dias",
                                                       "n_paginas": 1, "ocr_paginas": [],
                                                       "secciones_halladas": ["presupuesto"]})


class _Block:
    type = "text"

    def __init__(self, t):
        self.text = t


class _FakeClient:
    def __init__(self, texto):
        self._t = texto

    @property
    def messages(self):
        return self

    def create(self, **kw):
        return type("Msg", (), {"content": [_Block(self._t)]})()


def test_dry_estima_tokens(monkeypatch):
    _mock_texto(monkeypatch)
    r = capa_c.analizar_bases(pdf="x.pdf", dry=True)
    assert r["DRY_RUN"] is True
    assert r["tokens_estimados_entrada"] > 0


def test_parsea_json_de_la_respuesta(monkeypatch):
    _mock_texto(monkeypatch)
    monkeypatch.setattr(capa_c, "_client", lambda: _FakeClient('{"presupuesto": 50000000, "plazo_dias": 60}'))
    r = capa_c.analizar_bases(pdf="x.pdf")
    assert r["extraccion"]["presupuesto"] == 50000000
    assert r["extraccion"]["plazo_dias"] == 60


def test_respuesta_no_json_marca_parse_error(monkeypatch):
    _mock_texto(monkeypatch)
    monkeypatch.setattr(capa_c, "_client", lambda: _FakeClient("esto no es json"))
    r = capa_c.analizar_bases(pdf="x.pdf")
    assert r["extraccion"].get("_parse_error") is True


def _doc(c, cod, nombre, ruta, sha):
    c.execute("INSERT INTO documentos (codigo, nombre_archivo, ruta_local, tipo, bytes, sha256, "
              "fuente, descargado_at) VALUES (?,?,?,?,?,?,?,?)",
              (cod, nombre, ruta, ruta.rsplit(".", 1)[-1], 1, sha, "local", "t"))


def test_archivo_ilegible_se_saltea_y_sigue(tmp_path, monkeypatch):
    # un .docx (o PDF corrupto) mezclado NO debe tirar el análisis: se saltea y sigue con los PDFs
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "MIX", "nombre": "Mix"})
        _doc(c, "MIX", "bases.pdf", "/x/bases.pdf", "sha1")
        _doc(c, "MIX", "form.docx", "/x/form.docx", "sha2")

    def _texto(ruta, max_chars=12000):
        if ruta.endswith(".docx"):
            raise Exception("No /Root object! - Is this really a PDF?")
        return {"texto": "PRESUPUESTO 50M", "n_paginas": 1, "ocr_paginas": [], "secciones_halladas": []}

    monkeypatch.setattr(bases, "texto_para_analisis", _texto)
    monkeypatch.setattr(capa_c, "_client", lambda: _FakeClient('{"presupuesto": 50000000}'))
    r = capa_c.analizar_bases(codigo="MIX")
    assert not r.get("error")                                   # no tiró: el docx se salteó
    assert r["extraccion"]["presupuesto"] == 50000000          # analizó el PDF bueno
    assert any(m.get("error") for m in r["meta"])              # el saltado queda trazado
    assert any(m.get("paginas") == 1 for m in r["meta"])       # el legible también


def test_todos_ilegibles_devuelve_error(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "BAD", "nombre": "Bad"})
        _doc(c, "BAD", "roto.pdf", "/x/roto.pdf", "sha1")

    def _boom(ruta, max_chars=12000):
        raise Exception("Unexpected EOF")

    monkeypatch.setattr(bases, "texto_para_analisis", _boom)
    r = capa_c.analizar_bases(codigo="BAD")
    assert r.get("error") and r["meta"]                        # sin nada legible → error con traza
