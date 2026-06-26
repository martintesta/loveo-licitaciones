#!/usr/bin/env python
"""
review.py - Revisor ADVERSARIAL del diff. No aprueba: intenta romperlo.

Manda el diff a Claude con la instruccion de buscar bugs, casos borde y regresiones
-en especial del shim SQLite<->Postgres, secretos y los invariantes de CLAUDE.md-
e imprime hallazgos priorizados. Es ADVISORY: no bloquea el push (exit 0 siempre).
Corrlo antes de mergear y lee lo que encontro.

  python scripts/review.py                 # diff vs origin/master
  python scripts/review.py --staged        # solo lo staged
  python scripts/review.py HEAD~3          # vs un ref puntual

Modelo: LOVEO_REVIEW_MODEL (default claude-sonnet-4-6; mejor para cazar bugs que haiku).
Necesita ANTHROPIC_API_KEY (la toma del entorno o del registro de Windows, como la app).
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # para poder importar db.py (vive en la raiz, no en scripts/)
MAX_DIFF = 60000  # cap defensivo del tamano del diff

PROMPT = """Sos un revisor de codigo ADVERSARIAL. Tu trabajo NO es aprobar: es ROMPER este diff.
Proyecto: pipeline Python/Streamlit de licitaciones publicas (ChileCompra), backend SQLite/Postgres.

Invariantes del proyecto (violarlos ES un bug, reportalo):
- IDs nuevos -> "INSERT ... RETURNING id", nunca cur.lastrowid (devuelve None en Postgres).
- Conteo de booleanos -> SUM(CASE WHEN x THEN 1 ELSE 0 END), nunca SUM(x='y') (rompe en PG).
- Todo SQL pasa por db.conn(); pensa SIEMPRE el caso Postgres ademas del SQLite.
- NO reportes los placeholders '?' como bug de Postgres: db.conn() devuelve _PGConn, cuyo
  .execute() traduce '?'->'%s' e 'INSERT OR IGNORE'->'ON CONFLICT' automaticamente (db._prep).
  Los '?' en c.execute(...) son la convencion CORRECTA del proyecto.
- Secretos solo en .env / variables de entorno, jamas en codigo trackeado.
- El score es PROVISIONAL; las vistas no inventan data que no exista en el codigo MP real.

Busca, en orden de gravedad: bugs de correctitud, casos borde sin manejar, regresiones,
SQL que rompe en Postgres, secretos filtrados, y violaciones de los invariantes de arriba.
Para CADA hallazgo: `archivo:linea`, severidad [ALTA/MEDIA/BAJA], por que es problema, y el fix.
Si no hay nada serio, decilo en una sola linea. No elogies el codigo. Se conciso y directo.

DIFF A REVISAR:
"""


def _run(cmd):
    # encoding explicito: en Windows el default es cp1252 y revienta con UTF-8 del diff.
    return subprocess.run(cmd, cwd=ROOT, capture_output=True,
                          text=True, encoding="utf-8", errors="replace").stdout


def get_diff():
    if "--staged" in sys.argv:
        return _run(["git", "diff", "--staged"])
    base = next((a for a in sys.argv[1:] if not a.startswith("-")), "origin/master")
    return _run(["git", "diff", f"{base}...HEAD"]) or _run(["git", "diff", base])


def main():
    diff = (get_diff() or "").strip()
    if not diff:
        print("[review] No hay diff para revisar.")
        return 0
    if len(diff) > MAX_DIFF:
        print(f"[review] diff de {len(diff)} chars, recortado a {MAX_DIFF} para la revision.")
        diff = diff[:MAX_DIFF]

    try:
        import anthropic
    except ImportError:
        print("[review] Falta el paquete 'anthropic'. Salteo (advisory).")
        return 0

    if not os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import db  # noqa: F401  -- su import dispara _load_dotenv + winreg
        except Exception:
            pass
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[review] Sin ANTHROPIC_API_KEY. Salteo (advisory).")
        return 0

    model = os.environ.get("LOVEO_REVIEW_MODEL", "claude-sonnet-4-6")
    print(f"[review] revisando con {model}...\n" + "-" * 60)
    client = anthropic.Anthropic()
    try:
        with client.messages.stream(
            model=model,
            max_tokens=4000,
            messages=[{"role": "user", "content": PROMPT + diff}],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
        print("\n" + "-" * 60)
    except Exception as e:
        print(f"\n[review] No se pudo revisar con {model}: {e}")
        print("[review] Proba otro modelo: LOVEO_REVIEW_MODEL=claude-haiku-4-5 python scripts/review.py")
    return 0  # advisory: nunca bloquea


if __name__ == "__main__":
    sys.exit(main())
