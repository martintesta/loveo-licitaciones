# Desplegar el tablero en Render

La base ya está en **Neon** (Postgres). Esto hostea la **app** (Streamlit) y la conecta a esa base.
Archivos ya listos en el repo: `Dockerfile`, `.dockerignore`, `render.yaml`.

## 1) Subir el código a GitHub (repo PRIVADO)
Los secretos (`.env`, `config_local.py`, `credentials.json`, `token.json`) están en `.gitignore` → no se suben.
```bash
git add -A
git commit -m "Deploy: Dockerfile + render.yaml"
# creá el repo en github.com (privado) y luego:
git remote add origin https://github.com/<tu-usuario>/loveo-licitaciones.git
git branch -M main
git push -u origin main
```
(O con GitHub CLI: `gh repo create loveo-licitaciones --private --source=. --push`.)

## 2) Crear el Web Service en Render
1. Render → **New +** → **Web Service**.
2. **Connect** tu repo `loveo-licitaciones` de GitHub.
3. Render detecta el `Dockerfile` (Runtime = Docker). Dejá el resto por defecto. Plan: **Free** para arrancar.
4. **Create Web Service**.

## 3) Cargar los secretos (Environment → Environment Variables)
| Key | Valor |
|---|---|
| `DATABASE_URL` | el connection string de tu Neon |
| `ANTHROPIC_API_KEY` | tu API key de Claude (`sk-ant-...`) |
| `LOVEO_CHILECOMPRA_TICKET` | tu ticket de ChileCompra |
| `LOVEO_MODEL` | `claude-haiku-4-5` (opcional) |

**Opcional (Secret Files)** — Environment → Secret Files:
- `config_local.py` — para que el scoring use tu calibración real (tiers logística/cashflow). Si no lo subís, usa fallbacks.
- `service_account.json` — para leer Google Drive desde el server (cuenta de servicio; ver SETUP_DRIVE.md opción B). El `token.json` personal NO sirve en el server.

## 4) Deploy + probar
- Render construye y publica en una URL `https://loveo-licitaciones.onrender.com`.
- Abrila → pantalla de login (martin / la contraseña que pusiste).
- (Plan free: el primer acceso tras inactividad tarda ~40s en "despertar".)

## Notas
- **Descarga de bases (Capa B)**: sigue en el worker residencial (IP chilena), no en Render.
- Cada `git push` a `main` redespliega solo (autoDeploy).
- Para always-on (sin cold start) subí el plan a **Starter**.
