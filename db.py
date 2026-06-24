"""
db.py — Persistencia local-first (SQLite) del pipeline de licitaciones de Loveo.

Doble eje de estado (decisión vs resultado):
  estado_revision : nueva -> en_revision -> (descartada | aprobada)
  estado_resultado: (si aprobada) pendiente -> presentada -> (ganada | perdida | desierta)

Capas: A=descubrir/filtrar, admisibilidad, scoring provisional, B=descargar, C=scoring final.
Cada cambio relevante deja un registro en `eventos` (trazabilidad).
"""
import os
import sqlite3, time
from pathlib import Path

# Capa de datos configurable (H1 → producción):
#   - SQLite (default, local): ruta vía LOVEO_DB_PATH o ./loveo.db
#   - Postgres (prod): DATABASE_URL=postgresql://...  (backend pendiente de validar contra instancia real; ver docs/produccion.md §2.1)
def _load_dotenv(path=Path(__file__).parent / ".env"):
    """Carga .env (DATABASE_URL, etc.) sin pisar variables ya presentes. Self-contained para cualquier entry point."""
    if not path.exists():
        return
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k:
                os.environ.setdefault(k, v)
    # ANTHROPIC_API_KEY suele vivir en el entorno de USUARIO de Windows; traerla si falta (winreg).
    if not os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as _k:
                val, _ = winreg.QueryValueEx(_k, "ANTHROPIC_API_KEY")
                if val:
                    os.environ["ANTHROPIC_API_KEY"] = val
        except Exception:
            pass


_load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DB_PATH = Path(os.environ.get("LOVEO_DB_PATH", Path(__file__).parent / "loveo.db"))
STORAGE_DIR = Path(__file__).parent / "storage"

REVISION_STATES = {"nueva", "en_revision", "descartada", "aprobada"}
RESULTADO_STATES = {"pendiente", "presentada", "ganada", "perdida", "desierta"}


def backend():
    return "postgres" if DATABASE_URL.startswith(("postgres://", "postgresql://")) else "sqlite"


# ------------------------------------------------------------------ backend Postgres (compat)
class _Row:
    """Fila híbrida: soporta r[0] (índice) y r['col'] (clave), y dict(r)."""
    __slots__ = ("_c", "_v")

    def __init__(self, cols, vals):
        self._c = cols
        self._v = vals

    def __getitem__(self, k):
        return self._v[k] if isinstance(k, int) else self._v[self._c.index(k)]

    def keys(self):
        return self._c

    def get(self, k, d=None):
        try:
            return self[k]
        except (KeyError, ValueError, IndexError):
            return d


def _pg_rowfactory(cursor):
    cols = [c.name for c in cursor.description] if cursor.description else []
    return lambda values: _Row(cols, list(values))


def _prep(sql):
    """Traduce SQL SQLite → Postgres."""
    ignore = "INSERT OR IGNORE INTO" in sql
    s = sql.replace("INSERT OR IGNORE INTO", "INSERT INTO")
    s = s.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    s = s.replace("?", "%s")
    if ignore and "on conflict" not in s.lower():
        s = s.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    return s


class _PGConn:
    """Envoltorio que imita la superficie de sqlite3.Connection usada por el proyecto."""

    def __init__(self, raw):
        self._raw = raw

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        try:
            self._raw.commit() if et is None else self._raw.rollback()
        finally:
            self._raw.close()
        return False

    def execute(self, sql, params=()):
        cur = self._raw.cursor()
        cur.execute(_prep(sql), tuple(params) if params else None)
        return cur

    def executescript(self, script):
        cur = self._raw.cursor()
        for stmt in script.split(";"):
            s = stmt.strip()
            if s and not s.upper().startswith("PRAGMA"):
                cur.execute(_prep(s))
        return cur

    def cursor(self):
        return self._raw.cursor()

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        self._raw.close()


def conn():
    if backend() == "postgres":
        import psycopg
        raw = psycopg.connect(DATABASE_URL, autocommit=True, row_factory=_pg_rowfactory)
        return _PGConn(raw)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL;")
    c.execute("PRAGMA foreign_keys=ON;")
    return c


def init_db():
    STORAGE_DIR.mkdir(exist_ok=True)
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS licitaciones (
            codigo            TEXT PRIMARY KEY,
            nombre            TEXT NOT NULL,
            organismo         TEXT,
            region            TEXT,
            monto_estimado    REAL,
            moneda            TEXT,
            fecha_cierre      TEXT,
            fecha_visita      TEXT,
            tipo_pago         TEXT,
            estado_mp         INTEGER,
            descripcion       TEXT,
            prohibicion_subc  TEXT,
            subcontratacion   TEXT,
            direccion_visita  TEXT,
            json_detalle      TEXT,

            -- Admisibilidad (paso 3)
            admisible         INTEGER,        -- 1/0/NULL
            admisible_motivo  TEXT,
            vigente_oferta    INTEGER,        -- 1 si aún se puede postular

            -- Estado (doble eje)
            estado_revision   TEXT NOT NULL DEFAULT 'nueva',
            estado_resultado  TEXT,

            -- Scoring Atlas
            score_provisional INTEGER,        -- triage con data de API (paso 5a)
            score_total       INTEGER,        -- final con bases + cubicación (Capa C)
            score_decision    TEXT,           -- GO / NO-GO / CONDICIONAL
            score_json        TEXT,           -- desglose 6 dimensiones + razonamiento
            requiere_bases    INTEGER,        -- 1 si el score depende de docs/cubicación
            feedback_humano   TEXT,

            -- Descarga (Capa B)
            docs_estado       TEXT DEFAULT 'pendiente',
            docs_carpeta      TEXT,

            fecha_descubierta TEXT NOT NULL,
            fecha_actualizada TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS documentos (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo         TEXT NOT NULL REFERENCES licitaciones(codigo) ON DELETE CASCADE,
            nombre_archivo TEXT NOT NULL,
            ruta_local     TEXT NOT NULL,
            tipo           TEXT,
            bytes          INTEGER,
            sha256         TEXT,
            descargado_at  TEXT,
            fuente         TEXT,
            url            TEXT,
            UNIQUE(codigo, sha256)
        );

        CREATE TABLE IF NOT EXISTS eventos (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo  TEXT NOT NULL REFERENCES licitaciones(codigo) ON DELETE CASCADE,
            ts      TEXT NOT NULL,
            tipo    TEXT NOT NULL,
            detalle TEXT
        );

        CREATE TABLE IF NOT EXISTS runs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha      TEXT NOT NULL,        -- ddmmaaaa procesado
            ts         TEXT NOT NULL,
            total_dia  INTEGER,
            candidatos INTEGER,
            admisibles INTEGER,
            errores    INTEGER,
            UNIQUE(fecha)
        );

        CREATE INDEX IF NOT EXISTS idx_lic_revision ON licitaciones(estado_revision);
        CREATE INDEX IF NOT EXISTS idx_lic_admis    ON licitaciones(admisible);
        CREATE INDEX IF NOT EXISTS idx_lic_docs     ON licitaciones(docs_estado);
        CREATE INDEX IF NOT EXISTS idx_eventos_cod  ON eventos(codigo);
        """)


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def log_evento(c, codigo, tipo, detalle=""):
    c.execute("INSERT INTO eventos(codigo, ts, tipo, detalle) VALUES (?,?,?,?)",
              (codigo, _now(), tipo, detalle))


def upsert_licitacion(c, row: dict):
    existe = c.execute("SELECT codigo FROM licitaciones WHERE codigo=?", (row["codigo"],)).fetchone()
    now = _now()
    cols = ["nombre", "organismo", "region", "monto_estimado", "moneda", "fecha_cierre",
            "fecha_visita", "tipo_pago", "estado_mp", "descripcion", "prohibicion_subc",
            "subcontratacion", "direccion_visita", "json_detalle"]
    if existe:
        sets = ", ".join(f"{k}=?" for k in cols) + ", fecha_actualizada=?"
        c.execute(f"UPDATE licitaciones SET {sets} WHERE codigo=?",
                  [row.get(k) for k in cols] + [now, row["codigo"]])
        return "actualizada"
    else:
        c.execute(f"""INSERT INTO licitaciones (codigo, {", ".join(cols)},
                      estado_revision, fecha_descubierta, fecha_actualizada)
                      VALUES (?, {", ".join("?" for _ in cols)}, 'nueva', ?, ?)""",
                  [row["codigo"]] + [row.get(k) for k in cols] + [now, now])
        log_evento(c, row["codigo"], "descubierta", (row.get("nombre") or "")[:120])
        return "nueva"


def set_admisibilidad(c, codigo, admisible, motivo, vigente):
    c.execute("UPDATE licitaciones SET admisible=?, admisible_motivo=?, vigente_oferta=?, fecha_actualizada=? WHERE codigo=?",
              (1 if admisible else 0, motivo, 1 if vigente else 0, _now(), codigo))
    log_evento(c, codigo, "admisibilidad", f"{'ADMISIBLE' if admisible else 'INADMISIBLE'}: {motivo}")


def set_score_provisional(c, codigo, score, score_json, requiere_bases):
    c.execute("UPDATE licitaciones SET score_provisional=?, score_json=?, requiere_bases=?, fecha_actualizada=? WHERE codigo=?",
              (score, score_json, 1 if requiere_bases else 0, _now(), codigo))
    log_evento(c, codigo, "score", f"provisional={score}/120")


def record_run(c, fecha, total, candidatos, admisibles, errores):
    c.execute("""INSERT INTO runs(fecha, ts, total_dia, candidatos, admisibles, errores)
                 VALUES (?,?,?,?,?,?)
                 ON CONFLICT(fecha) DO UPDATE SET ts=excluded.ts, total_dia=excluded.total_dia,
                   candidatos=excluded.candidatos, admisibles=excluded.admisibles, errores=excluded.errores""",
              (fecha, _now(), total, candidatos, admisibles, errores))


def fechas_procesadas(c):
    return {r[0] for r in c.execute("SELECT fecha FROM runs").fetchall()}


def set_estado_revision(codigo, nuevo, detalle=""):
    assert nuevo in REVISION_STATES, f"estado_revision inválido: {nuevo}"
    with conn() as c:
        c.execute("UPDATE licitaciones SET estado_revision=?, fecha_actualizada=? WHERE codigo=?", (nuevo, _now(), codigo))
        if nuevo == "aprobada":
            c.execute("UPDATE licitaciones SET estado_resultado=COALESCE(estado_resultado,'pendiente') WHERE codigo=?", (codigo,))
        log_evento(c, codigo, "cambio_estado", f"revision -> {nuevo}. {detalle}")


def set_estado_resultado(codigo, nuevo, detalle=""):
    assert nuevo in RESULTADO_STATES, f"estado_resultado inválido: {nuevo}"
    with conn() as c:
        c.execute("UPDATE licitaciones SET estado_resultado=?, fecha_actualizada=? WHERE codigo=?", (nuevo, _now(), codigo))
        log_evento(c, codigo, "cambio_estado", f"resultado -> {nuevo}. {detalle}")


if __name__ == "__main__":
    init_db()
    print(f"Base inicializada en {DB_PATH}")
