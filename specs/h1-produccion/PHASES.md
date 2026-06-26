# PHASES: H1 — producción

## Fase 1 — Capa de datos (SQLite → Postgres/Neon)
- Entregable: `db.py` backend-agnóstico (shim de dialecto), datos migrados a Neon.
- Listo cuando: `python scripts/preflight.py` verde + smoke real con `TEST_DATABASE_URL`.
- Estado: [x] hecho (284 filas migradas)

## Fase 2 — Auth / login
- Entregable: login PBKDF2 + sesión persistente (cookie + tabla `sesiones`).
- Listo cuando: F5 no desloguea; usuarios seedeados.
- Estado: [x] hecho

## Fase 3 — Deploy (Render + Neon)
- Entregable: Dockerfile + render.yaml; URL pública con login; tema legible.
- Listo cuando: estado "Live" en Render y login OK en `loveo-licitaciones.onrender.com`.
- Estado: [~] en curso (login y tema arreglados; falta confirmar Live estable)

## Fase 4 — Worker residencial (Capa B + Ficha Comprador)
- Entregable: worker con IP chilena que descarga bases y lee Ficha Comprador (tras WAF).
- Listo cuando: una base real baja end-to-end desde el worker.
- Estado: [ ] pendiente

## Fase 5 — Cadencia de keywords + métricas de uso
- Entregable: revisión periódica del valor de cada keyword; trazabilidad de uso.
- Listo cuando: reporte de keywords y panel de métricas básico.
- Estado: [ ] pendiente
