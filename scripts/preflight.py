#!/usr/bin/env python
"""
preflight.py - Sensores deterministicos que corren antes de cada 'git push'
(via .git/hooks/pre-push). Bloquea el push si:

  1) hay secretos en archivos TRACKEADOS (API keys, conn strings con password, client_secret)
  2) ruff encuentra un bug real (nombre indefinido, sintaxis, redefinicion)
  3) algun test falla

Salida ASCII a proposito (las consolas de Windows ahogan los emojis).

  Reinstalar el hook (tras clonar el repo):  python scripts/preflight.py --install-hook
  Correr los chequeos a mano:                python scripts/preflight.py
  Emergencia (saltar el hook):               git push --no-verify   [desaconsejado]
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (etiqueta, patron). git grep busca SOLO en archivos trackeados = lo que se va a pushear.
SECRET_PATTERNS = [
    ("Anthropic API key", r"sk-ant-[A-Za-z0-9_-]{20,}"),
    ("OpenAI API key", r"sk-[A-Za-z0-9]{20,}T3BlbkFJ"),
    ("Postgres conn con password", r"postgres(?:ql)?://[^\s:@/]+:[^\s@/]+@"),
    ("Google client_secret", r'"client_secret"\s*:\s*"[A-Za-z0-9_-]{10,}"'),
    ("AWS access key", r"AKIA[0-9A-Z]{16}"),
]
# Lineas que NO son secretos reales (placeholders en docs, este propio archivo).
_SKIP = re.compile(r"(EJEMPLO|EXAMPLE|placeholder|TU-NUEVA|<tu|xxxx|scripts/preflight\.py)", re.I)


def _run(cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def scan_secrets():
    hits = []
    for label, pat in SECRET_PATTERNS:
        r = _run(["git", "grep", "-nIE", pat])
        if r.returncode == 0 and r.stdout.strip():
            for line in r.stdout.splitlines():
                if _SKIP.search(line):
                    continue
                hits.append(f"  [{label}] {line}")
    return hits


def install_hook():
    hook = ROOT / ".git" / "hooks" / "pre-push"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\nexec python scripts/preflight.py\n", encoding="utf-8", newline="\n")
    try:
        hook.chmod(0o755)
    except Exception:
        pass
    print(f"[ok] hook instalado en {hook}")
    return 0


def main():
    if "--install-hook" in sys.argv:
        return install_hook()

    failed = False

    secrets = scan_secrets()
    if secrets:
        print("[FAIL] secretos: posibles credenciales en archivos trackeados")
        print("\n".join(secrets))
        print("       -> sacalo del archivo (va en .env / vars de entorno) y reintenta")
        failed = True
    else:
        print("[ok]   secretos: limpio")

    r = _run([sys.executable, "-m", "ruff", "check", "."])
    if r.returncode != 0:
        print("[FAIL] ruff:")
        print((r.stdout or r.stderr).rstrip())
        failed = True
    else:
        print("[ok]   ruff: limpio")

    r = _run([sys.executable, "-m", "pytest", "-q"])
    if r.returncode != 0:
        print("[FAIL] tests:")
        print((r.stdout or "")[-2000:].rstrip())
        failed = True
    else:
        tail = (r.stdout or "").strip().splitlines()
        print(f"[ok]   tests: {tail[-1] if tail else 'verde'}")

    if failed:
        print("\nPUSH BLOQUEADO. Arregla lo de arriba y reintenta.")
        print("(Emergencia real: git push --no-verify)")
        return 1
    print("\nPreflight OK - push permitido.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
