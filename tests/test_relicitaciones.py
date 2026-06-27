"""
test_relicitaciones.py — Sensor del enlace desierta -> re-licitación (heurístico Jaccard).

jaccard() es puro. detectar() enlaza una desierta (estado_mp=7) con su re-licitación
(estado_mp 5/6/8, mismo comprador, nombre parecido sobre umbral, cierre posterior).

  python -m pytest tests/test_relicitaciones.py -q
"""
import db
import schema_v2
import relicitaciones


def test_jaccard_distingue_relicitacion_de_ruido():
    a = "ADQUISICION E INSTALACION BOX DENTAL CONTAINER CESFAM LA REINA"
    b = a + " SEGUNDO LLAMADO"                       # re-licitación real
    c = "CONSTRUCCION DE PARADERO EN AVENIDA PONIENTE"  # no relacionada
    assert relicitaciones.jaccard(a, b) >= 0.45
    assert relicitaciones.jaccard(a, c) < 0.45
    assert relicitaciones.jaccard("", "x") == 0.0     # sin tokens -> 0


def test_detectar_enlaza_misma_entidad_y_nombre(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v2.migrate()
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "D1", "nombre": "Box dental container CESFAM La Reina",
                                 "organismo": "Muni La Reina", "fecha_cierre": "2026-01-10", "estado_mp": 7})
        db.upsert_licitacion(c, {"codigo": "N1", "nombre": "Box dental container CESFAM La Reina segundo llamado",
                                 "organismo": "Muni La Reina", "fecha_cierre": "2026-02-10", "estado_mp": 5})
        db.upsert_licitacion(c, {"codigo": "X1", "nombre": "Construccion de paradero",
                                 "organismo": "Muni Otra", "fecha_cierre": "2026-02-10", "estado_mp": 5})

    assert relicitaciones.detectar() == 1   # solo D1->N1 (X1 es otro comprador)
    with db.conn() as c:
        r = c.execute("SELECT codigo_nueva, score_match FROM relicitaciones WHERE codigo_desierto='D1'").fetchone()
    assert r["codigo_nueva"] == "N1"
    assert r["score_match"] >= 0.45
