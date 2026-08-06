"""
test_informe.py — Sensor del export .xlsx (informe.py).

Ensambla lo que el sistema YA sabe de una licitación (header, score 6-D, análisis de Capa C,
cubicación) en un Excel con FÓRMULAS reales (no valores pegados): el subtotal de cada partida y
el margen deben recalcular si se edita cantidad/precio. No dispara research nuevo. Debe funcionar
aunque falten piezas (sin Capa C, sin cubicación) — la mayoría de las licitaciones reales están
incompletas.

  python -m pytest tests/test_informe.py -q
"""
import io
import json

from openpyxl import load_workbook

import db
import informe
import scoring
import schema_v3


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v3.migrate()


def _wb(b):
    return load_workbook(io.BytesIO(b))


def test_codigo_inexistente_da_error_no_crashea(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = informe.generar_xlsx("NO-EXISTE")
    assert isinstance(r, dict) and r.get("error")


def test_licitacion_sin_capa_c_ni_cubicacion_igual_genera(tmp_path, monkeypatch):
    """El caso más común hoy: la mayoría de las licitaciones no tienen ni Capa C ni cubicación."""
    _setup(tmp_path, monkeypatch)
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "A", "nombre": "Sala modular", "organismo": "Muni X",
                                 "region": "Maule", "monto_estimado": 50000000})
    r = informe.generar_xlsx("A")
    assert not isinstance(r, dict), f"no debería fallar: {r}"
    wb = _wb(r)
    assert wb.sheetnames == ["Resumen", "Cubicación"]


def test_informe_completo_incluye_score_capa_c_y_cubicacion(tmp_path, monkeypatch):
    """Caso rico: todo lo que el pipeline puede haber calculado, debe aparecer en el documento."""
    _setup(tmp_path, monkeypatch)
    sj = {"dimensiones": {"margen": {"score": 5, "evaluado": True},
                          "complejidad": {"score": 6, "evaluado": True}},
          "score_provisional": 60}
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "B", "nombre": "Container doble piso", "organismo": "Muni Y",
                                 "region": "Ñuble", "monto_estimado": 30000000})
        db.set_score_provisional(c, "B", 60, json.dumps(sj), False)
        ex = {"resumen": "Bases claras.", "criterios_evaluacion": [{"nombre": "Precio", "peso_pct": 60}],
              "requisitos_clave": ["Visita obligatoria"], "garantias": [{"tipo": "Seriedad", "monto_o_pct": "3%"}]}
        c.execute("INSERT INTO analisis_bases (codigo, ts, resumen, presupuesto_clp, plazo_dias, "
                  "json_extraccion) VALUES (?,?,?,?,?,?)",
                  ("B", "2026-08-01", "Bases claras.", 28000000, 45, json.dumps(ex)))
        c.execute("INSERT INTO cubicaciones (proyecto, codigo, origen, fecha) VALUES (?,?,?,?)",
                  ("B", "B", "ia", "2026-08-01"))
        cub_id = c.execute("SELECT id FROM cubicaciones WHERE codigo='B'").fetchone()[0]
        c.execute("INSERT INTO cubicacion_items (cubicacion_id, partida, grupo, descripcion, cantidad, "
                  "unidad, precio_unitario, total) VALUES (?,?,?,?,?,?,?,?)",
                  (cub_id, "1.1", "material", "Panel SIP", 20, "m2", 12000, 240000))
    wb = _wb(informe.generar_xlsx("B"))
    res = "\n".join(str(c.value) for row in wb["Resumen"].iter_rows() for c in row if c.value is not None)
    cub = "\n".join(str(c.value) for row in wb["Cubicación"].iter_rows() for c in row if c.value is not None)
    for esperado in ("Container doble piso", "Muni Y", "Bases claras", "Visita obligatoria", "Seriedad"):
        assert esperado in res, f"falta {esperado!r} en Resumen"
    for esperado in ("Panel SIP", 12000, 20):
        assert str(esperado) in cub, f"falta {esperado!r} en Cubicación"


def test_subtotal_y_margen_son_formulas_no_valores_pegados(tmp_path, monkeypatch):
    """El punto del Excel sobre el Word: si el usuario edita Cantidad o Precio, TODO debe
    recalcular solo. Verifica que las celdas clave sean fórmulas (empiezan con '=')."""
    _setup(tmp_path, monkeypatch)
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "C", "nombre": "X", "organismo": "O", "region": "R"})
        c.execute("INSERT INTO analisis_bases (codigo, ts, presupuesto_clp) VALUES (?,?,?)",
                  ("C", "2026-08-01", 5000000))
        c.execute("INSERT INTO cubicaciones (proyecto, codigo, origen, fecha) VALUES (?,?,?,?)",
                  ("C", "C", "ia", "2026-08-01"))
        cub_id = c.execute("SELECT id FROM cubicaciones WHERE codigo='C'").fetchone()[0]
        c.execute("INSERT INTO cubicacion_items (cubicacion_id, partida, grupo, descripcion, cantidad, "
                  "unidad, precio_unitario, total) VALUES (?,?,?,?,?,?,?,?)",
                  (cub_id, "1.1", "material", "Panel", 10, "m2", 5000, 50000))
    wb = _wb(informe.generar_xlsx("C"))
    ws = wb["Cubicación"]
    fila = next(r for r in ws.iter_rows() if any(c.value == "Panel" for c in r))
    total_cell = fila[5]  # columna F: Total
    assert str(total_cell.value).startswith("="), "el Total debe ser fórmula, no el valor 50000"
    # margen también debe ser fórmula (referencia a techo y costo, no un número pegado)
    margen_cells = [c.value for row in ws.iter_rows() for c in row
                    if isinstance(c.value, str) and c.value.startswith("=") and "-" in c.value]
    assert margen_cells, "el margen (techo - costo) debe ser una fórmula"

    # sanity check con LibreOffice/Excel no disponible en CI: al menos openpyxl re-parsea sin error
    # y el valor cacheado (si existiera) no contradice lo esperado — acá solo validamos la fórmula.
    assert "C" in str(total_cell.value) and "E" in str(total_cell.value)  # referencia cantidad × precio


def test_partidas_sin_precio_se_avisan(tmp_path, monkeypatch):
    """Si el margen no se puede cerrar, el informe no debe simular que sí (honestidad)."""
    _setup(tmp_path, monkeypatch)
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "D", "nombre": "X", "organismo": "O", "region": "R"})
        c.execute("INSERT INTO cubicaciones (proyecto, codigo, origen, fecha) VALUES (?,?,?,?)",
                  ("D", "D", "ia", "2026-08-01"))
        cub_id = c.execute("SELECT id FROM cubicaciones WHERE codigo='D'").fetchone()[0]
        c.execute("INSERT INTO cubicacion_items (cubicacion_id, partida, grupo, descripcion, cantidad, "
                  "unidad) VALUES (?,?,?,?,?,?)", (cub_id, "1.1", "material", "Sin precio", 5, "u"))
    wb = _wb(informe.generar_xlsx("D"))
    txt = "\n".join(str(c.value) for row in wb["Cubicación"].iter_rows() for c in row if c.value is not None)
    assert "sin precio" in txt.lower()


def test_triage_del_informe_coincide_con_scoring(tmp_path, monkeypatch):
    """El informe NUNCA debe decir un veredicto distinto al que calcula scoring.triage (fuente
    única que también usan el tablero y capac_score)."""
    _setup(tmp_path, monkeypatch)
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "E", "nombre": "X", "organismo": "O", "region": "R"})
        db.set_score_provisional(c, "E", 90, json.dumps({"dimensiones": {}, "score_provisional": 90}), False)
    wb = _wb(informe.generar_xlsx("E"))
    txt = "\n".join(str(c.value) for row in wb["Resumen"].iter_rows() for c in row if c.value is not None)
    assert scoring.triage(90) in txt   # "Priorizar"
