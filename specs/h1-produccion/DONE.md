# DONE: H1 — producción

- 2026-06-24 `76666da` — Capa de datos migrada a Neon (284 filas), login con cookie + sesiones, archivos de deploy (Dockerfile/render.yaml). Verificado: build_data + writes + competencia + cubicación contra la instancia real.
- 2026-06-25 `b1b8121` — Fix tema lavado del login (`.streamlit/config.toml` fuerza tema claro). Verificado: login legible en prod.
- 2026-06-25 `a47eeb0` — `credentials/` agregado a `.gitignore` (ticket + API key en texto plano). Verificado: `git check-ignore`.
- 2026-06-25 `84b3525` — Harness de sensores: pre-push hook + `scripts/preflight.py` (secretos/ruff/pytest) + `tests/test_postgres_compat.py` + `CLAUDE.md`. Verificado: hook bloqueó una key falsa; suite verde.
