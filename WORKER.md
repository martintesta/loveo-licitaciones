# Worker residencial (Capa B) — deploy

El worker baja las **bases** de las licitaciones admisibles (Capa B). Tiene que correr en una
máquina con **IP chilena residencial** (tu notebook), porque el endpoint de adjuntos de Mercado
Público bloquea accesos de datacenter (403 / captcha). La app en Render **no** hace esto; comparte
la misma base (Neon) y el worker la procesa aparte.

## Qué corre dónde
- **App (Render)** → UI, scoring, aprendizaje. NO baja bases.
- **Worker (tu notebook, IP CL)** → polling de la base + descarga de bases (Playwright).
- **Base (Neon)** → única, compartida por los dos vía `DATABASE_URL`.

## Setup (una vez, en la máquina residencial)
```bash
pip install -r requirements.txt
python -m playwright install chromium      # navegador para la Capa B

# misma base que la app:
#   .env  ->  DATABASE_URL=postgresql://...neon...
#   .env  ->  LOVEO_CHILECOMPRA_TICKET=tu-ticket

# calibrar la navegación código→ficha (si la grilla no entrega archivos):
python calibrate_ficha.py 2450-56-LE26
```

## Correr
```bash
python worker.py --once     # una pasada (probar)
python worker.py            # loop infinito (intervalo LOVEO_WORKER_INTERVAL seg; default 120)
```
El loop nunca muere por un error puntual: marca `docs_estado='error'` + deja traza en `eventos`
y sigue con la próxima.

## Estado / criterio
- Toma las licitaciones con `admisible=1 AND docs_estado='pendiente'`.
- `download.descargar_codigo` maneja `descargando → descargado`; el worker solo cubre el error.
- Los archivos quedan en `storage/<codigo>/` y se registran en `documentos`.

## Restricción
- Corré **un solo worker a la vez**. No hay locking (`SELECT ... FOR UPDATE SKIP LOCKED`): dos
  workers verían los mismos pendientes y bajarían lo mismo dos veces. Para un notebook residencial
  alcanza con uno; si algún día hace falta escalar, ahí sí conviene el claim atómico.

## Pendiente (lo que falta de tu lado / próximo paso)
- **Calibración de la ficha**: `download.py` necesita que `calibrate_ficha.py` fije el último
  selector de la grilla de adjuntos (correr local una vez).
- **Ficha Comprador** (`worker.ficha_comprador`, hoy `NotImplementedError`): leer el comportamiento
  de pago del comprador (quejas de no-pago a tiempo), también detrás del WAF. Alimentaría la señal
  `mal_pagador` del aprendizaje y el cash flow del score. Es el siguiente trabajo del worker.
- **Always-on**: para que baje solo, la máquina tiene que estar prendida; o programá `worker.py
  --once` con el Programador de tareas / cron en tu horario.
