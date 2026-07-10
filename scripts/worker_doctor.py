"""
worker_doctor.py — Chequeo de salud del worker residencial (Capa B + C).

Corré ESTO en la máquina residencial ANTES de dejar el worker corriendo. Valida, sin exponer
secretos, que estén todos los ingredientes y te dice EXACTAMENTE qué falta:

  - DATABASE_URL apunta a Neon (Postgres), no al SQLite local (si no, el worker poliría vacío).
  - LOVEO_CHILECOMPRA_TICKET propio (no el público de prueba, rate-limited).
  - ANTHROPIC_API_KEY presente (Capa C la necesita).
  - Playwright + Chromium instalados (Capa B los usa).
  - La base conecta y el esquema está migrado.
  - Cuántas licitaciones esperan Capa B / Capa C ahora mismo.

  python scripts/worker_doctor.py        # exit 0 si está listo; 1 si falta algo crítico

Igual que preflight/review, la salida es tolerante a cp1252 (consola Windows).
"""
import os
import sys
import pathlib

# Correr desde la raíz del proyecto (donde vive .env) sin importar desde dónde se invoque.
ROOT = pathlib.Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

import config  # noqa: E402  (para TICKET / USANDO_TICKET_PRUEBA; db carga el .env por su cuenta)
import db      # noqa: E402


OK, WARN, FAIL = "[ok]  ", "[warn]", "[FALTA]"


def _check_database_url():
    url = db.DATABASE_URL
    if not url:
        return FAIL, "DATABASE_URL vacío → el worker usaría SQLite LOCAL (base vacía). Poné la de Neon en .env."
    if not url.startswith(("postgres://", "postgresql://")):
        return FAIL, f"DATABASE_URL no parece Postgres (empieza con '{url[:10]}…'). Debe ser la de Neon."
    return OK, f"DATABASE_URL → Postgres (Neon). backend={db.backend()}"


def _check_ticket():
    # No exponemos ni un fragmento del ticket: este output puede compartirse/capturarse.
    if config.USANDO_TICKET_PRUEBA:
        return WARN, "Ticket PÚBLICO de prueba (rate-limited). Poné LOVEO_CHILECOMPRA_TICKET propio en .env."
    return OK, "Ticket propio configurado."


def _check_api_key():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return FAIL, "ANTHROPIC_API_KEY ausente → la Capa C no puede analizar (worker solo bajaría bases)."
    return OK, "ANTHROPIC_API_KEY presente (Capa C habilitada)."


def _check_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return FAIL, "playwright no instalado. Corré: pip install -r requirements.txt"
    try:
        with sync_playwright() as p:
            path = p.chromium.executable_path
        if path and os.path.exists(path):
            return OK, "Playwright + Chromium instalados (Capa B lista)."
        return FAIL, "Chromium no instalado. Corré: python -m playwright install chromium"
    except Exception as e:
        return FAIL, f"Chromium no disponible ({type(e).__name__}). Corré: python -m playwright install chromium"


def _check_db_y_cola():
    try:
        import schema_v3
        import worker
        schema_v3.migrate()
        with db.conn() as c:
            c.execute("SELECT 1").fetchone()
        capa_b = len(worker.pendientes())
        capa_c = len(worker.pendientes_capac())
        return OK, f"Base conecta y migrada. Cola: Capa B {capa_b} · Capa C {capa_c}."
    except Exception as e:
        return FAIL, f"No se pudo consultar la base: {type(e).__name__}: {e}"


CHECKS = [
    ("Base de datos", _check_database_url),
    ("Ticket ChileCompra", _check_ticket),
    ("API key (Capa C)", _check_api_key),
    ("Playwright (Capa B)", _check_playwright),
    ("Conexión + cola", _check_db_y_cola),
]


def main():
    print("== Doctor del worker residencial ==\n")
    critico = False
    for nombre, fn in CHECKS:
        try:
            estado, detalle = fn()
        except Exception as e:  # un check nunca debe tumbar el doctor
            estado, detalle = FAIL, f"error inesperado: {type(e).__name__}: {e}"
        print(f"{estado} {nombre}: {detalle}")
        if estado == FAIL:
            critico = True

    print()
    if critico:
        print("RESULTADO: faltan cosas CRÍTICAS (marcadas [FALTA]). Arreglalas y reintentá.")
        print("Guía completa: WORKER.md")
        return 1
    print("RESULTADO: listo para correr el worker →  python worker.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
