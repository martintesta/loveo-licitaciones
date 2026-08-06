"""
test_config.py — Sensor del cargador de config (.env + contrato de constantes).

Cubre _cargar_dotenv (parseo, comillas, no-pisar-entorno, archivo inexistente) y que config
exponga las constantes que consumen otros módulos. os.environ se aísla con una copia por test.

  python -m pytest tests/test_config.py -q
"""
import os

import config


def test_cargar_dotenv_parsea_y_quita_comillas(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "environ", os.environ.copy())
    env = tmp_path / ".env"
    env.write_text('FOO=bar\n# comentario\nSIN_IGUAL\nQUOTED="con espacios"\n', encoding="utf-8")
    config._cargar_dotenv(str(env))
    assert os.environ["FOO"] == "bar"
    assert os.environ["QUOTED"] == "con espacios"   # comillas quitadas
    assert "SIN_IGUAL" not in os.environ            # líneas sin '=' se ignoran


def test_cargar_dotenv_no_pisa_el_entorno(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "environ", os.environ.copy())
    os.environ["YA"] = "del_entorno"
    env = tmp_path / ".env"
    env.write_text("YA=del_archivo\n", encoding="utf-8")
    config._cargar_dotenv(str(env))
    assert os.environ["YA"] == "del_entorno"        # setdefault: el entorno manda sobre el archivo


def test_cargar_dotenv_archivo_inexistente_no_crashea(tmp_path):
    config._cargar_dotenv(str(tmp_path / "no_existe.env"))


def test_config_expone_el_contrato():
    assert isinstance(config.TICKET, str) and config.TICKET
    assert isinstance(config.USANDO_TICKET_PRUEBA, bool)
    assert isinstance(config.DIAS_HACIA_ATRAS, int)
    assert hasattr(config, "KEYWORDS_INCLUIR")       # la calibración quedó cargada (real o ejemplo)


def test_discover_usa_el_ticket_de_config_no_uno_propio():
    """Regresión: discover pedía TICKET a config_local junto con las keywords. Como config_local NO
    define TICKET, el import fallaba ENTERO y se caía al ticket PÚBLICO de pruebas (rate-limited)
    aunque hubiera uno propio en .env — en silencio, con 429 intermitentes."""
    import discover
    assert discover.TICKET == config.TICKET, "discover debe usar el ticket de config (.env)"
