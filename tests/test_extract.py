"""
test_extract.py — Sensor de extract.extraer (json_detalle de MP -> adjudicaciones/items/competidores).

Alimenta un detalle mínimo (sin red) y verifica que se pueblan las tablas. Contra sqlite temporal.

  python -m pytest tests/test_extract.py -q
"""
import db
import schema_v2
import extract


def test_extraer_adjudicacion_items_y_competidor(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v2.migrate()
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "L1", "nombre": "x"})

    det = {
        "Adjudicacion": {"Fecha": "2026-01-01", "Numero": "A1", "NumeroOferentes": 3, "UrlActa": "http://x"},
        "Items": {"Listado": [
            {"NombreProducto": "Contenedor", "Cantidad": 2, "UnidadMedida": "u",
             "Adjudicacion": {"RutProveedor": "11.111.111-1", "NombreProveedor": "PABYMAC", "MontoUnitario": 100}},
        ]},
    }
    extract.extraer("L1", det)

    with db.conn() as c:
        adj = c.execute("SELECT n_oferentes FROM adjudicaciones WHERE codigo='L1'").fetchone()
        it = c.execute("SELECT nombre_proveedor, monto_total FROM items WHERE codigo='L1'").fetchone()
        part = c.execute("SELECT resultado FROM participaciones WHERE codigo='L1'").fetchone()
        comp = c.execute("SELECT razon_social FROM competidores WHERE rut='11.111.111-1'").fetchone()
    assert adj["n_oferentes"] == 3
    assert it["nombre_proveedor"] == "PABYMAC"
    assert it["monto_total"] == 200            # cantidad * monto_unitario
    assert part["resultado"] == "ganada"
    assert comp["razon_social"] == "PABYMAC"
