# Roadmap a producción — loveo-licitaciones

> De prototipo local-first (Streamlit + SQLite, una máquina) a web app usable en la realidad.
> H1 = usable por el equipo (interno, semanas). H2 = vendible (SaaS, meses).
> Marcá `[x]` lo hecho. Última edición: 2026-06-20.

---

## 0. Estado actual (qué YA sirve, reusable)
- ✅ Motor: pipeline (descubrir/filtrar/admisibilidad/score), modelo de datos, `run_daily`.
- ✅ Integraciones: API ChileCompra, Google Drive (OAuth, lectura de carpetas), Claude (Capa C + asistente text-to-SQL).
- ✅ Scoring provisional + Capa C (analizar bases → complejidad + techo de presupuesto).
- ✅ Tablero consola (tablero3.py) con acciones, drill-down, ficha, documentos, asistente.
- ✅ Ingestión de cubicación (Excel de Valentina) → catálogo de precios + trazabilidad.

El **motor no se tira**; lo que falta es infra (hosting, auth, DB, jobs, secretos) + decisiones de arquitectura.

---

## 1. La restricción que DEFINE la arquitectura: IP residencial
La Capa B (descarga de bases) y la Ficha Comprador chocan con **WAF/captcha desde datacenter** (403).
→ No se pueden correr en la nube. La arquitectura es **híbrida**:
- **Nube**: UI + API + DB + jobs no-sensibles (descubrir/score/Capa C/asistente).
- **Worker residencial (CL)**: tareas IP-sensibles (descarga de bases, Ficha Comprador). Un agente que corre
  en una máquina/conexión chilena (o proxy residencial) y se comunica con la nube por cola/HTTP.

Este worker es el **cuello de botella #1**: sin él, la descarga no escala fuera de la notebook.

---

## 2. H1 — Usable por el equipo (interno)
Objetivo: que vos y Valentina lo usen en serio, hosteado, sin rebuild. Streamlit se queda.

- [x] **Capa de datos configurable** (`DATABASE_URL`): `db.py` abstrae SQLite (dev) o **Postgres** (prod) con shim de compat. ✅
- [x] **Postgres gestionado** (Neon, São Paulo) + **migración de datos** (`migrate_to_postgres.py`, 284 filas) + validado (build_data, escrituras, competencia, cubicación). La app corre sobre Neon vía `.env`. ✅
- [ ] **Backups** automáticos del Postgres (Neon tiene point-in-time básico; definir política).
- [ ] **Autenticación / usuarios** (Martín, Valentina) con roles; gate del tablero.
- [ ] **Deploy**: VPS (o PaaS) + HTTPS + dominio. Streamlit detrás de reverse proxy.
- [ ] **Secretos fuera de archivos locales**: API key, OAuth Drive por usuario, ticket ChileCompra → variables/secrets manager encriptado.
- [ ] **Worker residencial de descargas** (Capa B + Ficha Comprador): agente local que toma trabajos y sube resultados.
- [ ] **Jobs programados**: `run_daily` diario + scoring (cron/worker). IP-sensibles → al worker residencial.
- [ ] **Cash flow por reputación de pago** (vía worker → Ficha Comprador). Ver spec rediseño §5.
- [ ] **Observabilidad básica**: logs centralizados, manejo de errores/reintentos, alerta si falla la corrida diaria.
- [ ] **Controles de costo LLM**: cuotas/tope mensual, caché (Capa C ya cachea; asistente no).

### 2.1 Plan de port a Postgres (inventario, para ejecutar contra instancia real)
Estado: **COMPLETADO y validado contra Neon** (Postgres 18). El backend se elige por `DATABASE_URL`.
- [x] **DDL**: `AUTOINCREMENT` → `SERIAL` (traducción en el shim de `db.py`).
- [x] **Upsert**: `INSERT OR IGNORE` → `ON CONFLICT DO NOTHING` (traducido en el shim).
- [x] **PRAGMA**: omitido en PG.
- [x] **`lastrowid`** → `RETURNING id` (cubicacion.py portable).
- [x] **Placeholders** `?` → `%s` (shim).
- [x] **Row factory** híbrida (`row["col"]` y `row[0]`).
- [x] **`SUM(bool)`** (sqlite) → `SUM(CASE WHEN …)` en `competencia.resumen` (bug PG).
- [x] **Migración de datos** (`migrate_to_postgres.py`) + reset de secuencias.
- [x] **Validación**: `tests/` (SQLite), build_data + escrituras + competencia + cubicación (PG).
> SQLite sigue como fallback local (sin `DATABASE_URL`). Pendiente menor: validar `run_daily` (pipeline) completo sobre PG.

### 2.2 Trazabilidad de uso y valor (gratis, sin suscripción)
Para decidir H2 (y para mejorar H1) hace falta medir **adopción** y **valor** — todo con datos PROPIOS, $0:
- **Ya existe**: la tabla `eventos` registra cada acción (descubierta, score, cambio_estado, feedback, documento, capa_c, nota). Es un log de auditoría/uso listo.
- **Falta (barato)**: una vista **"Métricas de uso"** en el tablero que agregue ese log:
  - *Adopción*: licitaciones revisadas/semana, aprobadas vs descartadas, análisis Capa C corridos, preguntas al asistente, días activos.
  - *Valor (lo que importa para H2)*: fit descubiertas, presentadas, **ganadas/perdidas** (de `estado_resultado`), **win rate**, **monto ganado**, tiempo-a-decisión.
- **Opcional más adelante**: PostHog tiene free tier (product analytics, funnels) si se quiere algo más fino — pero el log propio + la vista alcanzan para validar H1→H2 sin pagar nada.
- Costo de IA (transparencia): loguear tokens por corrida de Capa C / asistente para ver el gasto real.

### 2.3 Para que lo usen OTROS USUARIOS (camino corto, interno)
Hoy corre en `localhost` (solo vos). Para que lo use el equipo (Valentina, etc.) — la DB ya está en Neon:
- [ ] **Login / usuarios** (en progreso): tabla `usuarios` + gate de acceso + roles (admin/analista). ← arrancando.
- [ ] **Deploy**: hostear la UI (VPS/PaaS) + HTTPS + dominio. La DB ya es remota.
- [ ] **Atribución por usuario**: registrar *quién* hizo cada acción en `eventos`.
- [ ] **Worker residencial** (uno solo) para descargas de bases — los demás usuarios usan la UI normal.
- [ ] **Secretos en el host** (API key, ticket, Drive) — no archivos locales. Decidir Drive compartido vs por usuario.
> Mínimo para "otros lo usan" = **login + deploy** (lo caro, la DB en la nube, ya está hecho). Multi-empresa/venta = H2.

## 3. H2 — Vendible (SaaS)  ·  **OPCIONAL — A VALIDAR SEGÚN RESULTADOS DE H1**
> H2 NO es una fase comprometida. Es una apuesta de negocio que solo se activa si H1 demuestra valor
> y hay demanda. No invertir en H2 (multi-tenant, auth-platform, facturación) antes de validar.
>
> **Gatillos para decidir H2** (medidos con la trazabilidad de H1, ver §2.2):
> - H1 genuinamente ayuda a ganar: tasa de presentación/ganadas sube, tiempo-a-decisión baja.
> - Uso sostenido del equipo (no se abandona tras la novedad).
> - Señal de mercado: otras empresas piden/pagarían por esto.
> Si esos tres no se cumplen → quedarse en H1 ya es ganar.

Objetivo (si se valida): que un cliente externo se suscriba y use sin que toquemos nada.

- [ ] **Front web real** (React/Next) + **API** sobre el motor Python (FastAPI). Streamlit queda solo interno.
- [ ] **Multi-tenant**: aislamiento de datos por empresa (org_id en todo; Postgres con RLS o esquema por tenant).
- [ ] **Onboarding self-service**: cada cliente conecta su **ticket ChileCompra**, su **Drive**, define **keywords/exclusiones**, sus **bases logísticas** y su **cubicación**. Hoy todo está hardcodeado a Loveo (`config_local.py`).
- [ ] **Facturación / planes / cuotas** (Stripe u otro) + límites de uso LLM por plan.
- [ ] **Cubicación tipo automática** (margen estimado: specs Capa C + `precios_referencia` + web). Ver spec rediseño §8.
- [ ] **Roles/permisos** por organización (admin, analista, comercial).
- [ ] **Cumplimiento/seguridad**: política de datos, borrado, auditoría de accesos.

## 4. Completitud de producto (transversal, no infra)
- [ ] Cubicación tipo → margen estimado (cierra el GO/NO-GO).
- [ ] Subir PDF directo (no solo link de Drive).
- [ ] Kanban interactivo, Mapa logístico, Desiertas/Inteligencia con datos.
- [ ] Estabilizar el worker de descargas (calibración de selectores, captcha).

---

## 5. Orden sugerido (H1)
1. **Capa de datos configurable** (SQLite↔Postgres) — desbloquea todo el deploy.
2. **Autenticación** — prerequisito de uso real/multiusuario.
3. **Deploy** (VPS + Postgres + HTTPS) + **secretos**.
4. **Worker residencial** + **jobs diarios**.
5. Observabilidad + costos.

## 6. Decisiones abiertas
- ❓ Dónde hostear (VPS propio vs PaaS) y dónde el Postgres.
- ❓ Forma del worker residencial (agente custom vs proxy residencial CL).
- ❓ Cuándo cortar a front React (H2) vs estirar Streamlit.
