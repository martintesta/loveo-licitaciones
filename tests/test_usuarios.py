"""
test_usuarios.py — Sensor de la capa de auth (hash de contraseña + sesiones).

Security-critical: una regresión acá = hueco de seguridad o lockout. Cubre el hash
(nunca en claro), verify (correcta/incorrecta/inactivo) y el ciclo de sesión
(crear/validar/borrar/expirar/token inválido). Contra SQLite temporal (no toca Neon).

  python -m pytest tests/test_usuarios.py -q
"""
import db
import schema_v3
import usuarios


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v3.migrate()  # tablas usuarios + sesiones


def test_add_y_verify_roundtrip(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    usuarios.add("ana", "Ana", "secreta123", "analista")
    u = usuarios.verify("ana", "secreta123")
    assert u and u["username"] == "ana" and u["rol"] == "analista"


def test_verify_pass_incorrecta_y_usuario_inexistente(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    usuarios.add("ana", "Ana", "secreta123")
    assert usuarios.verify("ana", "otra") is None
    assert usuarios.verify("nadie", "x") is None


def test_hash_nunca_guarda_la_pass_en_claro(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    usuarios.add("ana", "Ana", "secreta123")
    with db.conn() as c:
        r = c.execute("SELECT pass_hash, salt FROM usuarios WHERE username='ana'").fetchone()
    assert "secreta123" not in (r["pass_hash"] or "")
    assert r["salt"]  # hay salt único


def test_set_password_invalida_la_anterior(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    usuarios.add("ana", "Ana", "vieja")
    usuarios.set_password("ana", "nueva")
    assert usuarios.verify("ana", "vieja") is None
    assert usuarios.verify("ana", "nueva")


def test_usuario_inactivo_no_verifica(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    usuarios.add("ana", "Ana", "x")
    with db.conn() as c:
        c.execute("UPDATE usuarios SET activo=0 WHERE username='ana'")
    assert usuarios.verify("ana", "x") is None


def test_sesion_crear_validar_borrar(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    usuarios.add("ana", "Ana", "x", "admin")
    tok = usuarios.crear_sesion("ana")
    u = usuarios.validar_sesion(tok)
    assert u and u["username"] == "ana" and u["rol"] == "admin"
    usuarios.borrar_sesion(tok)
    assert usuarios.validar_sesion(tok) is None


def test_sesion_token_invalido_o_none(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert usuarios.validar_sesion("token-que-no-existe") is None
    assert usuarios.validar_sesion(None) is None


def test_sesion_expirada_no_valida(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    usuarios.add("ana", "Ana", "x")
    tok = usuarios.crear_sesion("ana")
    with db.conn() as c:  # forzar expiración en el pasado
        c.execute("UPDATE sesiones SET expira=? WHERE token=?", ("2000-01-01 00:00:00", tok))
    assert usuarios.validar_sesion(tok) is None


# ---------------------------------------------------------------- roles / autorización (#5)
def test_es_admin():
    assert usuarios.es_admin({"rol": "admin"}) is True
    assert usuarios.es_admin({"rol": "analista"}) is False
    assert usuarios.es_admin(None) is False


def test_permitido_acciones_admin_only():
    admin = {"rol": "admin"}
    analista = {"rol": "analista"}
    for acc in usuarios.ACCIONES_ADMIN:          # kw_add, kw_toggle, error_resuelto
        assert usuarios.permitido(admin, acc) is True
        assert usuarios.permitido(analista, acc) is False
        assert usuarios.permitido(None, acc) is False


def test_permitido_flujo_diario_para_todos():
    analista = {"rol": "analista"}
    for acc in ("seguir", "aprobar", "descartar", "resultado:ganada", "cubic_ia",
                "cubic_guardar", "rep_pago", "add_codigo", "recall"):
        assert usuarios.permitido(analista, acc) is True


def test_permitido_falla_cerrado_sin_usuario():
    assert usuarios.permitido(None, "aprobar") is False   # fail-closed: sin sesión, nada
    assert usuarios.permitido(None, "kw_add") is False
