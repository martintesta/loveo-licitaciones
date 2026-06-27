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
