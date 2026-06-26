"""
test_capac_drive.py — Sensores de drive.parse_link (puro) y capac_score.estimar (degradación).

  python -m pytest tests/test_capac_drive.py -q
"""
import db
import drive


def test_parse_link_carpeta():
    assert drive.parse_link("https://drive.google.com/drive/folders/ABC123_def-456") == ("folder", "ABC123_def-456")


def test_parse_link_archivo():
    assert drive.parse_link("https://drive.google.com/file/d/FILE_id-789/view") == ("file", "FILE_id-789")


def test_parse_link_id_con_query():
    assert drive.parse_link("https://drive.google.com/open?id=QWErty_12-34") == ("file", "QWErty_12-34")


def test_parse_link_id_pelado():
    assert drive.parse_link("1A2b3C4d5E6f7G8h9I0jKLMNOP") == ("file", "1A2b3C4d5E6f7G8h9I0jKLMNOP")


def test_parse_link_basura():
    assert drive.parse_link("no es un link") == (None, None)
    assert drive.parse_link("") == (None, None)
    assert drive.parse_link(None) == (None, None)


def test_estimar_codigo_inexistente_no_crashea(tmp_path, monkeypatch):
    """Capa C en seco sobre un código sin bases: error claro, nunca una excepción que tumbe la app."""
    import capac_score
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    r = capac_score.estimar("NO-EXISTE-123")
    assert isinstance(r, dict) and "ok" in r
    assert r["ok"] is False
