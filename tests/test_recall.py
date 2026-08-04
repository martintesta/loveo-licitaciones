"""Tests de M-3 (red ancha de recall léxico) + auditoría de recall del discovery (recall.py, #3)."""
import pytest

import db
import recall
import schema_v3
from filters import es_candidata_recall, keywords_amplio_que_matchean


def test_solo_amplio_cae_en_recall():
    # "posta" es término amplio y NO está en la lista estricta de INCLUIR.
    nombre = "Construcción posta rural Llanada Grande"
    assert keywords_amplio_que_matchean(nombre) != []
    assert es_candidata_recall(nombre) is True


def test_estricto_no_cae_en_recall():
    # "container" es keyword estricta -> va al output normal, NO a recall.
    nombre = "Adquisición de container para bodega municipal"
    assert es_candidata_recall(nombre) is False


def test_sin_match_no_cae_en_recall():
    assert es_candidata_recall("Servicio de aseo de oficinas") is False


# ------------------------------------------------ auditoría de recall del discovery (recall.py, #3)
@pytest.fixture
def _kws(monkeypatch):
    """Listas fijas para no depender de la tabla keywords ni de config_local."""
    inc = ["container", "modular", "reas"]
    exc = ["herramienta", "viga"]
    amp = ["posta", "policlinico"]
    monkeypatch.setattr("keywords.get_active_lists", lambda: (inc, exc, amp))


def _db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v3.migrate()


def test_clasificar_estricto(_kws):
    assert recall.clasificar("Provisión de container modular")[0] == "estricto"


def test_clasificar_excluido_por_exclusion(_kws):
    # matchea INCLUIR (modular) pero también EXCLUIR (herramienta) -> posible sobre-exclusión
    b, kw = recall.clasificar("Modular con herramientas")
    assert b == "excluido"
    assert "herramienta" in kw


def test_clasificar_recall_solo_red_amplia(_kws):
    # 'posta' está en AMPLIO y no en la estricta -> candidata a revisar (falso negativo)
    b, kw = recall.clasificar("Construcción de posta rural")
    assert b == "recall"
    assert kw == ["posta"]


def test_clasificar_irrelevante(_kws):
    assert recall.clasificar("Servicio de jardinería")[0] == "irrelevante"


def test_registrar_solo_graba_accionables(_kws, tmp_path, monkeypatch):
    _db(monkeypatch, tmp_path)
    listado = [
        {"CodigoExterno": "E1", "Nombre": "container modular"},          # estricto -> NO se graba
        {"CodigoExterno": "R1", "Nombre": "posta rural"},               # recall   -> graba
        {"CodigoExterno": "X1", "Nombre": "modular con herramientas"},  # excluido -> graba
        {"CodigoExterno": "I1", "Nombre": "jardinería y áreas verdes"},  # irrelevante -> NO
    ]
    with db.conn() as c:
        counts = recall.registrar_descartes(c, listado, "08072026")
    assert counts == {"estricto": 1, "recall": 1, "excluido": 1, "irrelevante": 1}
    aud = recall.auditar()
    assert aud["pendientes"] == 2 and aud["recall"] == 1 and aud["excluido"] == 1
    assert {i["codigo"] for i in aud["items"]} == {"R1", "X1"}


def test_registrar_idempotente_por_codigo_y_run(_kws, tmp_path, monkeypatch):
    _db(monkeypatch, tmp_path)
    listado = [{"CodigoExterno": "R1", "Nombre": "posta rural"}]
    with db.conn() as c:
        recall.registrar_descartes(c, listado, "08072026")
        recall.registrar_descartes(c, listado, "08072026")  # mismo run -> no duplica
    assert recall.auditar()["pendientes"] == 1


def test_resolver_saca_de_la_cola(_kws, tmp_path, monkeypatch):
    _db(monkeypatch, tmp_path)
    with db.conn() as c:
        recall.registrar_descartes(c, [{"CodigoExterno": "R1", "Nombre": "posta rural"}], "08072026")
    recall.resolver("R1", "descartada")
    assert recall.auditar()["pendientes"] == 0


def test_resolver_accion_invalida():
    with pytest.raises(ValueError):
        recall.resolver("R1", "cualquiera")


def _sembrar_recall(codigos, nombre="posta rural"):
    with db.conn() as c:
        recall.registrar_descartes(c, [{"CodigoExterno": k, "Nombre": nombre} for k in codigos], "08072026")


def test_sugerencia_de_keyword_por_promociones(_kws, tmp_path, monkeypatch):
    # 4 licitaciones que solo pescó la red amplia ('posta'); el usuario promovió 3 → sugerir subirla
    _db(monkeypatch, tmp_path)
    _sembrar_recall(["R1", "R2", "R3", "R4"])
    for k in ("R1", "R2", "R3"):
        recall.resolver(k, "promovida")
    recall.resolver("R4", "descartada")
    sug = recall.sugerencias_keywords(min_apariciones=3, min_confianza=0.6)
    assert len(sug) == 1
    s = sug[0]
    assert s["termino"] == "posta" and s["apariciones"] == 4
    assert s["promovidas"] == 3 and s["descartadas"] == 1 and s["confianza"] == 0.75
    # y viaja en el payload de la UI
    assert recall.auditar()["sugerencias"][0]["termino"] == "posta"


def test_sugerencia_cuenta_por_licitacion_no_por_corrida(_kws, tmp_path, monkeypatch):
    """Auditoría: hay una fila por (codigo, fecha_run). Una lic que reaparece muchos días NO debe
    inflar apariciones/confianza (antes: 1 lic promovida en 3 corridas + 1 descartada → conf 0.75
    y sugería; en realidad son 2 licitaciones decididas 50/50)."""
    _db(monkeypatch, tmp_path)
    with db.conn() as c:                              # A aparece en 3 corridas distintas, B en 1
        for run in ("01072026", "02072026", "03072026"):
            recall.registrar_descartes(c, [{"CodigoExterno": "A", "Nombre": "posta rural"}], run)
        recall.registrar_descartes(c, [{"CodigoExterno": "B", "Nombre": "posta rural"}], "01072026")
    recall.resolver("A", "promovida")
    recall.resolver("B", "descartada")
    sug = recall.sugerencias_keywords(min_apariciones=2, min_confianza=0.6)
    assert sug == []                                  # 1 promovida / 2 licitaciones = 0.5 < 0.6
    todas = recall.sugerencias_keywords(min_apariciones=2, min_confianza=0.0)
    assert todas[0]["apariciones"] == 2               # 2 licitaciones, no 4 filas
    assert todas[0]["promovidas"] == 1 and todas[0]["confianza"] == 0.5


def test_no_sugiere_lo_mayormente_descartado(_kws, tmp_path, monkeypatch):
    _db(monkeypatch, tmp_path)
    _sembrar_recall(["R1", "R2", "R3"])
    recall.resolver("R1", "promovida")
    for k in ("R2", "R3"):
        recall.resolver(k, "descartada")            # confianza 1/3 < 0.6 → no se sugiere
    assert recall.sugerencias_keywords() == []


def test_no_sugiere_lo_ya_en_incluir(_kws, tmp_path, monkeypatch):
    # se sembró y promovió como amplio; una vez que 'posta' YA está en INCLUIR, no hay nada que sugerir
    _db(monkeypatch, tmp_path)
    _sembrar_recall(["R1", "R2", "R3"])
    for k in ("R1", "R2", "R3"):
        recall.resolver(k, "promovida")
    assert recall.sugerencias_keywords()[0]["termino"] == "posta"        # antes: se sugiere
    monkeypatch.setattr("keywords.get_active_lists", lambda: (["container", "posta"], [], ["posta"]))
    assert recall.sugerencias_keywords() == []                          # ya en INCLUIR: nada que aprender


def test_exclusion_aprendida_baja_a_excluido(_kws, monkeypatch, tmp_path):
    """Paridad con discover.matchea: una lic vetada por una exclusión APRENDIDA no debe quedar
    'estricto' (falso negativo silencioso), sino 'excluido' → auditable."""
    aprendidas = tmp_path / "exclusiones_aprendidas.txt"
    aprendidas.write_text("bodega reciclada\n", encoding="utf-8")
    import discover
    monkeypatch.setattr(discover, "_LEARNED_FILE", aprendidas)
    b, kw = recall.clasificar("container bodega reciclada")   # container=incluir, pero aprendida veta
    assert b == "excluido"
    assert "bodega reciclada" in kw
