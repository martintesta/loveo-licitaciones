# Calibración Capa B (descarga de adjuntos) — loveo-licitaciones

Sondeado contra el portal real el **2026-06-16**.

## Hallazgo que cambió el supuesto
El portal `www.mercadopublico.cl` ahora responde **200 desde datacenter** (antes documentábamos 403).
La ficha se puede leer desde cualquier lado. Pero el **endpoint de archivos sí está protegido**.

## Ruta verificada (selectores reales)

| Paso | Cómo | Estado |
|---|---|---|
| 1. Ficha | `…/Modules/RFB/DetailsAcquisition.aspx?idlicitacion=<CODIGO>` | ✅ 200. El servidor resuelve solo el token `qs=`. `idlicitacion` en **minúscula** (el código viejo usaba `idLicitacion`). |
| 2. Token de adjuntos | en la ficha, `#imgAdjuntos` → `onclick="open('../Attachment/ViewAttachment.aspx?enc=<TOKEN>', …)"` | ✅ Extraído por regex. |
| 3. Lista de archivos | abrir `…/Modules/Attachment/ViewAttachment.aspx?enc=<TOKEN>` | ❌ desde datacenter dispara el **muro anti-bot** ("actividad anormal"). |
| 4. Descargar cada archivo | controles de la grilla de ViewAttachment | ❓ pendiente de mapear (paso 3 bloqueado acá). |

## Por qué el resto corre en tu máquina (y no es evasión)
El muro "actividad anormal" es la protección anti-bot de ChileCompra. **No se evade.** Las bases son
data pública de licitaciones a las que te presentás; descargarlas desde **tu IP residencial con un
navegador normal** es uso genuino y no dispara la protección. `download.py` ya quedó calibrado con los
pasos 1 y 2 reales; el 3–4 se ejecuta donde el acceso es legítimo.

## Qué quedó en el código
- `download.py` — ruta calibrada (ficha `idlicitacion` → `enc` → ViewAttachment), detección del muro,
  y si la grilla no entrega archivos, guarda `_viewattachment.html` para cerrar el último selector.
- `calibrate_ficha.py` — sonda local enfocada en el paso 3–4: abre ViewAttachment, dumpea su DOM y lista
  los controles de descarga.

## Runbook (en tu notebook, IP residencial CL — 10 min)
```bash
pip install playwright && python -m playwright install chromium
# 1) intentar la descarga directa de una publicada con adjuntos:
python download.py 2450-56-LE26
```
- Si bajan archivos → listo, Capa B operativa. (Si da el muro con HEADLESS=True, poné `HEADLESS=False` en download.py.)
- Si la grilla no entrega archivos → cerramos el último selector:
```bash
python calibrate_ficha.py 2450-56-LE26
```
  y me mandás `calibration/viewattachment.html`. Con eso fijo el selector de descarga y queda 100%.

## Pendiente real tras esto
Con los archivos en disco se habilita: **Capa C** (lectura de bases con Claude API → score FINAL de
margen y complejidad) y el **Asistente IA Nivel 3** (preguntas sobre el contenido de las bases).
El GO/NO-GO final igual necesita la **cubicación de Valentina**, no solo el texto.
