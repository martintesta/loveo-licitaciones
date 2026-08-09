"""
test_cad.py — Lectura de planos DWG/DXF (cad.py), sin depender de tener ODA File Converter
instalado: arma un DXF sintético en memoria con ezdxf y lo escribe a disco para probar
extraer_dxf/texto_para_analisis contra un archivo real. La conversión DWG->DXF (que sí
necesita el binario externo) se prueba solo en el camino de error ("no instalado").

  python -m pytest tests/test_cad.py -q
"""
import pytest

ezdxf = pytest.importorskip("ezdxf")

import cad


def _dxf_sintetico(tmp_path):
    doc = ezdxf.new()
    doc.layers.add("COTAS")
    doc.layers.add("EQUIPOS")
    msp = doc.modelspace()
    msp.add_text("CONTENEDOR MODULAR 6.00 x 2.40", dxfattribs={"layer": "EQUIPOS"})
    msp.add_blockref("PUERTA", (0, 0))
    msp.add_blockref("PUERTA", (5, 0))
    msp.add_blockref("VENTANA", (2, 0))
    ruta = tmp_path / "plano.dxf"
    doc.saveas(ruta)
    return str(ruta)


def test_extraer_dxf_lee_texto_bloques_y_capas(tmp_path):
    ruta = _dxf_sintetico(tmp_path)
    ex = cad.extraer_dxf(ruta)
    assert "CONTENEDOR MODULAR 6.00 x 2.40" in ex["texto"]
    assert ex["bloques"] == {"PUERTA": 2, "VENTANA": 1}
    assert "COTAS" in ex["capas"] and "EQUIPOS" in ex["capas"]
    assert ex["archivo_dwg"] is None                 # ya era .dxf, no hubo conversión
    assert ex["archivo_dxf"] == ruta


def test_texto_para_analisis_mismo_shape_que_bases(tmp_path):
    ruta = _dxf_sintetico(tmp_path)
    r = cad.texto_para_analisis(ruta, max_chars=12000)
    assert set(r) >= {"texto", "n_paginas", "ocr_paginas", "secciones_halladas"}
    assert r["n_paginas"] is None
    assert r["ocr_paginas"] == []
    assert r["secciones_halladas"] == ["plano_cad"]
    assert "CONTENEDOR MODULAR" in r["texto"]
    assert "PUERTA×2" in r["texto"]                   # bloques repetidos, formateados nombre×cantidad


def test_texto_para_analisis_respeta_max_chars(tmp_path):
    ruta = _dxf_sintetico(tmp_path)
    r = cad.texto_para_analisis(ruta, max_chars=50)
    assert len(r["texto"]) <= 50


def test_convertir_a_dxf_sin_oda_instalado_da_error_claro(tmp_path, monkeypatch):
    monkeypatch.setattr(cad, "_encontrar_oda", lambda: None)
    falso_dwg = tmp_path / "plano.dwg"
    falso_dwg.write_bytes(b"no importa, no llega a leerse")
    with pytest.raises(RuntimeError, match="ODA File Converter"):
        cad.convertir_a_dxf(str(falso_dwg))


def test_convertir_a_dxf_cachea_si_dxf_es_mas_nuevo(tmp_path):
    dwg = tmp_path / "plano.dwg"
    dwg.write_bytes(b"x")
    dxf = tmp_path / "plano.dxf"
    dxf.write_bytes(b"y")
    import os, time
    os.utime(dwg, (time.time() - 100, time.time() - 100))
    assert cad.convertir_a_dxf(str(dwg)) == str(dxf)  # no llama a ODA: ya hay .dxf más nuevo
