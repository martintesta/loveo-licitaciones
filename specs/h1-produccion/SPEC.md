# SPEC: H1 — producción para uso del equipo

## Problema
El tablero corría solo local (SQLite, sin login, sin hosting). Valentina y el equipo
no podían usarlo, y cualquier corte de la PC se llevaba el estado.

## Objetivo
App multiusuario hosteada, con datos persistentes y login estable.

## Alcance
- Incluye: capa de datos Postgres (Neon), login con sesión persistente, deploy (Render),
  worker residencial para Capa B + Ficha Comprador, trazabilidad de uso.
- NO incluye (esto es H2, opcional/a validar): SaaS multi-tenant facturado, onboarding self-serve.

## Criterios de aceptación (exit 0 = pasa)
- [x] Capa de datos andando en Postgres -> `TEST_DATABASE_URL=<branch> python -m pytest tests/ -q`
- [x] Login persiste tras F5 -> validación manual en la URL pública
- [x] Sin regresiones SQLite↔Postgres -> `python scripts/preflight.py`
- [ ] Capa B descarga bases desde IP residencial CL (worker)
- [ ] Cadencia de revisión de keywords + métricas de uso

## Invariantes a respetar
Ver `CLAUDE.md` (sección INVARIANTES). Críticos acá: shim Postgres (lastrowid/SUM), secretos
en `.env`, score provisional, worker residencial para Capa B.

## Riesgos / decisiones abiertas
- Plan free de Render se duerme (~50s de cold start). Subir a Starter si molesta.
- El worker residencial necesita una máquina con IP chilena siempre prendida.
