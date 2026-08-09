"""
test_cubicacion.py — Sensor del parser/ingesta del Excel de cubicación.

Genera un xlsx mínimo con openpyxl, lo ingiere, y verifica el cálculo de margen + que el
INSERT ... RETURNING id (el fix portable Postgres) funcionó. Más tests puros de _grupo.

  python -m pytest tests/test_cubicacion.py -q
"""
import openpyxl

import cubicacion
import db
import schema_v3


def test_grupo_clasifica():
    assert cubicacion._grupo("MANO DE OBRA", "maestro") == "mano_obra"
    assert cubicacion._grupo("Flete", "traslado a obra") == "transporte"
    assert cubicacion._grupo("Estructura Acero", "perfil") == "material"


def test_ingest_xlsx_minimo(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v3.migrate()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Ingreso con IVA", 119.0])
    ws.append(["Ingreso sin IVA", 100.0])
    ws.append(["Costo Total", 50.0])
    # fila de ítem: A vacía, B=partida, C=desc, D=cant, E=unidad, F=precio_unit, G=total
    ws.append(["", "Estructura Acero", "Perfil 100x100", 10, "u", 5.0, 50.0])
    xlsx = tmp_path / "cub.xlsx"
    wb.save(xlsx)

    r = cubicacion.ingest(str(xlsx), proyecto="Test", codigo="L1")
    assert r["items"] == 1
    assert r["ingreso_sin_iva"] == 100.0
    assert r["costo_total"] == 50.0
    assert r["margen"] == 50.0

    with db.conn() as c:
        cub = c.execute("SELECT id, costo_total FROM cubicaciones WHERE proyecto='Test'").fetchone()
        n = c.execute("SELECT COUNT(*) FROM cubicacion_items WHERE cubicacion_id=?", (cub["id"],)).fetchone()[0]
    assert cub["id"] is not None   # RETURNING id funcionó (no lastrowid)
    assert n == 1
    assert r["tendencias"] == []   # primera vez que se ve este material: nada con qué comparar


def _xlsx_un_item(path, desc, precio):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Ingreso con IVA", 119.0])
    ws.append(["Ingreso sin IVA", 100.0])
    ws.append(["Costo Total", precio * 10])
    ws.append(["", "Estructura Acero", desc, 10, "u", precio, precio * 10])
    wb.save(path)


def test_ingest_reporta_tendencia_si_el_material_se_repite_mas_caro(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v3.migrate()

    x1 = tmp_path / "proy1.xlsx"
    _xlsx_un_item(x1, "Perfil 100x100", 5.0)
    cubicacion.ingest(str(x1), proyecto="Proyecto1", codigo="L1")

    x2 = tmp_path / "proy2.xlsx"
    _xlsx_un_item(x2, "Perfil 100x100", 6.0)   # mismo material, +20%, otro proyecto
    r2 = cubicacion.ingest(str(x2), proyecto="Proyecto2", codigo="L2")

    assert len(r2["tendencias"]) == 1
    t = r2["tendencias"][0]
    assert t["descripcion"] == "Perfil 100x100" and t["direccion"] == "sube" and t["variacion_pct"] == 20.0
