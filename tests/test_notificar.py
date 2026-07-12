"""
test_notificar.py — Sensor de los avisos de deadline (notificar.py, cierra M-2).

Verifica el filtro de candidatas (en juego + dentro del umbral), el dedup (no re-avisar), y que
correr() arme+mande+registre con un sender INYECTADO (no se envía ni un mail; no toca SMTP ni Neon).

  python -m pytest tests/test_notificar.py -q
"""
from datetime import datetime, timedelta

import db
import notificar
import schema_v3

HOY = datetime(2026, 7, 10, 9, 0, 0)


def _fecha(dias):
    return (HOY + timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%S")


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v3.migrate()


def _lic(codigo, **kw):
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": codigo, "nombre": kw.get("nombre", "Lic " + codigo),
                                 "organismo": kw.get("organismo", "Muni X"),
                                 "region": kw.get("region", "Maule"),
                                 "fecha_cierre": kw.get("cierre"), "fecha_visita": kw.get("visita")})
        if kw.get("rev"):
            c.execute("UPDATE licitaciones SET estado_revision=? WHERE codigo=?", (kw["rev"], codigo))
        if kw.get("res"):
            c.execute("UPDATE licitaciones SET estado_resultado=? WHERE codigo=?", (kw["res"], codigo))


def test_candidatas_solo_en_ventana_y_en_juego(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _lic("A", cierre=_fecha(3))                 # cierra en 3 -> alerta
    _lic("B", cierre=_fecha(30))                # lejos -> fuera
    _lic("C", cierre=_fecha(-2))                # ya cerró -> fuera
    _lic("D", cierre=_fecha(2), rev="descartada")   # descartada -> fuera
    _lic("E", cierre=_fecha(2), res="presentada")   # ya presentada -> fuera
    _lic("F", visita=_fecha(1))                 # visita mañana -> alerta
    cods = {(x["codigo"], x["tipo"]) for x in notificar.candidatas(hoy=HOY, umbral=5)}
    assert cods == {("A", "cierre"), ("F", "visita")}


def test_candidatas_cierre_y_visita_de_la_misma_lic(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _lic("A", cierre=_fecha(4), visita=_fecha(1))
    tipos = sorted(x["tipo"] for x in notificar.candidatas(hoy=HOY, umbral=5))
    assert tipos == ["cierre", "visita"]        # un aviso por evento


def test_correr_envia_una_vez_y_deja_de_avisar(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _lic("A", cierre=_fecha(3))
    enviados = []
    cap = lambda asunto, cuerpo, dest: enviados.append((asunto, cuerpo, dest))

    r1 = notificar.correr(hoy=HOY, umbral=5, enviar=cap)
    assert r1 == {"candidatas": 1, "nuevas": 1, "enviado": True, "worker_stale": False}
    assert len(enviados) == 1
    assert "A" in enviados[0][1]                 # el código aparece en el cuerpo

    r2 = notificar.correr(hoy=HOY, umbral=5, enviar=cap)   # segunda pasada: ya avisada
    assert r2["nuevas"] == 0 and r2["enviado"] is False
    assert len(enviados) == 1                     # NO se reenvió


def test_worker_mudo_dispara_aviso_una_vez_al_dia(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    import worker
    worker.registrar_salud(pendientes=5, bajadas=0, capac=0, muro=True)   # backlog + muro = stale
    # forzar staleness: sin ultimo_ok, salud() ya lo marca stale
    enviados = []
    cap = lambda a, cuerpo, d: enviados.append(cuerpo)

    r1 = notificar.correr(hoy=HOY, umbral=5, enviar=cap)   # no hay deadlines, pero sí worker mudo
    assert r1["enviado"] is True and r1["worker_stale"] is True
    assert "WORKER MUDO" in enviados[0] and "muro anti-bot" in enviados[0]

    r2 = notificar.correr(hoy=HOY, umbral=5, enviar=cap)   # mismo día: no re-avisa
    assert r2["enviado"] is False
    assert len(enviados) == 1


def test_envio_fallido_no_registra_y_reintenta(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _lic("A", cierre=_fecha(3))

    def _falla(*a):
        raise RuntimeError("SMTP caído")

    r = notificar.correr(hoy=HOY, umbral=5, enviar=_falla)
    assert r["enviado"] is False and "falló el envío" in r["error"]
    # NO se registró → sigue siendo 'nueva' para el próximo intento
    assert notificar.nuevas(notificar.candidatas(hoy=HOY, umbral=5))


def test_correr_sin_nuevas_no_arma_nada(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _lic("A", cierre=_fecha(30))                  # nada en ventana
    llamado = []
    r = notificar.correr(hoy=HOY, umbral=5, enviar=lambda *a: llamado.append(a))
    assert r["enviado"] is False and not llamado


def test_deadline_que_cambia_re_notifica(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _lic("A", cierre=_fecha(3))
    notificar.correr(hoy=HOY, umbral=5, enviar=lambda *a: None)
    # el organismo movió el cierre -> nueva fecha_evento -> vuelve a ser 'nueva'
    with db.conn() as c:
        c.execute("UPDATE licitaciones SET fecha_cierre=? WHERE codigo='A'", (_fecha(2),))
    frescas = notificar.nuevas(notificar.candidatas(hoy=HOY, umbral=5))
    assert any(x["codigo"] == "A" for x in frescas)


def test_render_arma_asunto_y_cuerpo():
    items = [{"codigo": "1509-12-LR26", "nombre": "Módulos", "organismo": "Muni Y",
              "region": "Ñuble", "score": 88, "tipo": "cierre", "fecha": "2026-07-13T16:00:00", "dias": 3}]
    asunto, cuerpo = notificar.render(items)
    assert "1 deadline" in asunto
    assert "1509-12-LR26" in cuerpo and "score 88" in cuerpo


def test_disponible_refleja_env(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.setenv("LOVEO_ALERT_TO", "a@b.cl")
    assert notificar.disponible() is False        # falta SMTP_HOST
    monkeypatch.setenv("SMTP_HOST", "smtp.test")
    assert notificar.disponible() is True
