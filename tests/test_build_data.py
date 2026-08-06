"""
test_build_data.py — Smoke del único camino de lectura de la UI (tablero_data.build_data).

build_data() es lo que alimenta TODA la consola. Un import roto o un SQL que falla acá
tumba la app entera. Este smoke lo corre contra sqlite temporal vacío y verifica que
devuelve la estructura esperada sin crashear.

  python -m pytest tests/test_build_data.py -q
"""
import db


def test_build_data_devuelve_estructura(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    import tablero_data
    data = tablero_data.build_data()
    for k in ("lics", "order", "groups", "intel", "metricas", "keywords", "aprendizaje", "meta"):
        assert k in data, f"falta la key {k}"
    assert isinstance(data["lics"], dict)
    assert isinstance(data["order"], list)
    assert isinstance(data["groups"], dict)
    # el panel de aprendizaje siempre trae su umbral (aunque no haya descartes)
    assert "umbral" in data["aprendizaje"]
    assert "actualizado" in data  # freshness de los datos


def test_un_panel_roto_no_mata_el_tablero(tmp_path, monkeypatch):
    """QA: un error en build_data es PERMANENTE (la app no carga NUNCA, como pasó con el user
    dict → SQL). Los paneles opcionales deben degradarse, no tumbar todo."""
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    import plan
    import recall
    import worker
    import tablero_data

    def _explota(*a, **k):
        raise RuntimeError("panel roto")

    monkeypatch.setattr(recall, "auditar", _explota)
    monkeypatch.setattr(worker, "salud", _explota)
    monkeypatch.setattr(plan, "preferencias", _explota)
    data = tablero_data.build_data()          # antes: RuntimeError → tablero muerto
    assert data["recall"] == {} and data["worker"] == {} and data["plan"] == []
    assert isinstance(data["lics"], dict)     # el resto del tablero sigue vivo


def test_incompleto_marca_lics_sin_detalle(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "SINDET", "nombre": "solo codigo y nombre"})   # sin json_detalle
        db.upsert_licitacion(c, {"codigo": "CONDET", "nombre": "con detalle", "json_detalle": "{}"})
    import tablero_data
    data = tablero_data.build_data()
    assert data["lics"]["SINDET"]["incompleto"] is True   # extracción incompleta -> badge "SIN DETALLE"
    assert data["lics"]["CONDET"]["incompleto"] is False
    assert data["actualizado"]  # hay fecha de actualización


def test_build_data_expone_confianza_del_score(tmp_path, monkeypatch):
    """Fase C: cada lic scoreada trae cuántas de las 6 dimensiones tienen dato real
    (evDims/nDims) y los puntos evaluables (evalPts), para leer el score con su confianza."""
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    import json
    import scoring
    sj = scoring.score_provisional({"nombre": "container modular", "region": "Región Metropolitana",
                                    "modalidad": 3})
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "SC1", "nombre": "container modular",
                                 "region": "Región Metropolitana"})
        db.set_score_provisional(c, "SC1", sj["score_provisional"], json.dumps(sj), sj["requiere_bases"])
    import tablero_data
    l = tablero_data.build_data()["lics"]["SC1"]
    assert l["nDims"] == 6
    assert l["evDims"] == 4                       # margen y complejidad quedan pendientes de bases
    assert l["evalPts"] == sj["evaluable_pts"]    # puntos con dato real, no placeholder


def test_build_data_expone_requisitos_de_admisibilidad(tmp_path, monkeypatch):
    """#3: build_data surfacea garantías + requisitos_clave de la Capa C (json_extraccion) como
    checklist, para no quedar inadmisible por un papel faltante."""
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    import json
    import schema_v3
    schema_v3.migrate()
    ex = {"garantias": [{"tipo": "Seriedad de la oferta", "monto_o_pct": "3%"}, "Fiel cumplimiento"],
          "requisitos_clave": ["Visita a terreno obligatoria", "Experiencia mínima 3 obras",
                               "Inscripción en ChileProveedores"]}
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "R1", "nombre": "x"})
        c.execute("INSERT INTO analisis_bases (codigo, ts, json_extraccion) VALUES (?,?,?)",
                  ("R1", "2026-07-10", json.dumps(ex)))
    import tablero_data
    a = tablero_data.build_data()["lics"]["R1"]["analisis"]
    assert "Seriedad de la oferta: 3%" in a["garantias"]
    assert "Fiel cumplimiento" in a["garantias"]
    assert "Visita a terreno obligatoria" in a["requisitos"]
    assert "Inscripción en ChileProveedores" in a["requisitos"]


def test_build_data_requisitos_string_no_se_rompe_en_caracteres(tmp_path, monkeypatch):
    """Regresión #4: si el LLM devuelve un STRING donde esperamos lista, NO debe iterar caracteres."""
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    import json
    import schema_v3
    schema_v3.migrate()
    ex = {"requisitos_clave": "Visita obligatoria", "garantias": "Boleta 5%"}   # strings, no listas
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "S1", "nombre": "x"})
        c.execute("INSERT INTO analisis_bases (codigo, ts, json_extraccion) VALUES (?,?,?)",
                  ("S1", "2026-07-10", json.dumps(ex)))
    import tablero_data
    a = tablero_data.build_data()["lics"]["S1"]["analisis"]
    assert a["requisitos"] == ["Visita obligatoria"]      # un item, NO ['V','i','s',...]
    assert a["garantias"] == ["Boleta 5%"]


def test_build_data_no_repite_el_trabajo_pesado(tmp_path, monkeypatch):
    """Perf: migrate() está cacheado por base, así que el DDL (db.init_db) corre UNA sola vez
    pese a múltiples build_data y a que muchos módulos llaman migrate()."""
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    import schema_v3
    import tablero_data
    key = str(tmp_path / "t.db")
    schema_v3._MIGRATED.discard(key)
    tablero_data._INIT_DONE.discard(key)

    n = {"c": 0}
    orig = db.init_db
    monkeypatch.setattr(db, "init_db", lambda: (n.__setitem__("c", n["c"] + 1), orig())[1])

    tablero_data.build_data()
    tablero_data.build_data()
    assert n["c"] == 1   # el trabajo pesado del schema corre una sola vez por proceso/base
