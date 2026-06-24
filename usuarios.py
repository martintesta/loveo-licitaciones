"""
usuarios.py — Login / usuarios (H1: para que lo use el equipo).

Hash de contraseña con PBKDF2-SHA256 (stdlib, sin dependencias). Roles: admin | analista.

  seed_if_empty()        — crea martin (admin) y valentina (analista) con contraseña TEMPORAL.
  verify(user, pass)     — devuelve el dict del usuario o None.
  add / set_password     — alta y cambio de contraseña.

CLI:
  python usuarios.py list
  python usuarios.py add <username> "<Nombre>" <admin|analista>      (pide contraseña)
  python usuarios.py passwd <username>                                (pide contraseña)
"""
import os
import hashlib
import secrets
import datetime
import db
import schema_v3

SESSION_DAYS = 14  # cuánto dura la sesión persistente (cookie)

PASS_TEMP = "loveo.2026"  # TEMPORAL — cambiar tras el primer login (python usuarios.py passwd <user>)


def _hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 200_000).hex()


def add(username, nombre, password, rol="analista"):
    schema_v3.migrate()
    salt = secrets.token_hex(16)
    with db.conn() as c:
        c.execute("""INSERT OR IGNORE INTO usuarios(username, nombre, rol, salt, pass_hash, activo, creado_at)
                     VALUES (?,?,?,?,?,1,?)""",
                  (username.strip().lower(), nombre, rol, salt, _hash(password, salt), db._now()))


def set_password(username, password):
    salt = secrets.token_hex(16)
    with db.conn() as c:
        c.execute("UPDATE usuarios SET salt=?, pass_hash=? WHERE username=?",
                  (salt, _hash(password, salt), username.strip().lower()))


def verify(username, password):
    with db.conn() as c:
        r = c.execute("SELECT username, nombre, rol, salt, pass_hash, activo FROM usuarios WHERE username=?",
                      (username.strip().lower(),)).fetchone()
    if not r or not r["activo"] or not r["salt"]:
        return None
    if secrets.compare_digest(_hash(password, r["salt"]), r["pass_hash"]):
        return {"username": r["username"], "nombre": r["nombre"], "rol": r["rol"]}
    return None


def crear_sesion(username):
    """Crea un token de sesión persistente y lo guarda. Devuelve el token."""
    schema_v3.migrate()
    token = secrets.token_urlsafe(32)
    expira = (datetime.datetime.now() + datetime.timedelta(days=SESSION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    with db.conn() as c:
        c.execute("INSERT INTO sesiones(token, username, expira, creado_at) VALUES (?,?,?,?)",
                  (token, username, expira, db._now()))
    return token


def validar_sesion(token):
    """Devuelve el usuario si el token existe y no expiró; si no, None (y limpia el expirado)."""
    if not token:
        return None
    with db.conn() as c:
        r = c.execute("SELECT username, expira FROM sesiones WHERE token=?", (token,)).fetchone()
        if not r:
            return None
        if r["expira"] and r["expira"] < db._now():
            c.execute("DELETE FROM sesiones WHERE token=?", (token,))
            return None
        u = c.execute("SELECT username, nombre, rol, activo FROM usuarios WHERE username=?", (r["username"],)).fetchone()
    if not u or not u["activo"]:
        return None
    return {"username": u["username"], "nombre": u["nombre"], "rol": u["rol"]}


def borrar_sesion(token):
    if not token:
        return
    with db.conn() as c:
        c.execute("DELETE FROM sesiones WHERE token=?", (token,))


def listar():
    schema_v3.migrate()
    with db.conn() as c:
        return [dict(r) for r in c.execute("SELECT username, nombre, rol, activo FROM usuarios ORDER BY username").fetchall()]


def seed_if_empty():
    schema_v3.migrate()
    with db.conn() as c:
        n = c.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
    if n:
        return 0
    add("martin", "Martín Testa", PASS_TEMP, "admin")
    add("valentina", "Valentina", PASS_TEMP, "analista")
    return 2


if __name__ == "__main__":
    import sys
    import getpass
    a = sys.argv[1:]
    if not a or a[0] == "list":
        for u in listar():
            print(f"  {u['username']:12} {u['rol']:9} {'activo' if u['activo'] else 'inactivo'}  {u['nombre']}")
    elif a[0] == "add" and len(a) >= 4:
        add(a[1], a[2], getpass.getpass("Contraseña: "), a[3])
        print("usuario creado")
    elif a[0] == "passwd" and len(a) >= 2:
        set_password(a[1], getpass.getpass("Nueva contraseña: "))
        print("contraseña actualizada")
    else:
        print(__doc__)
