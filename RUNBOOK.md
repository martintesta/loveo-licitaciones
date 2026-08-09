# RUNBOOK — loveo-licitaciones (de punta a punta)

Comandos exactos en orden. No hace falta reconstruir nada: seguí los bloques.

## Qué corre dónde
- **Capa A** (descubrir + score) → la API de ChileCompra responde **desde cualquier lado**. Usa tu ticket.
- **Capa B** (descargar bases) → **LOCAL, en tu notebook** (IP residencial CL). El endpoint de adjuntos
  bloquea accesos automatizados de datacenter; desde tu casa es uso genuino.
- **Capa C** (leer bases con IA) → local, necesita tu `ANTHROPIC_API_KEY`. Manda **solo texto** (barato).

---

## 1) SETUP — una sola vez

```bash
# dependencias Python
pip install -r requirements.txt
python -m playwright install chromium          # navegador para Capa B

# OCR para Capa C (PDFs escaneados) — según tu sistema:
#   macOS:   brew install tesseract tesseract-lang
#   Ubuntu:  sudo apt install tesseract-ocr tesseract-ocr-spa
#   Windows: instalar "Tesseract-OCR" (UB Mannheim) + paquete de idioma español

# credenciales locales (NO se suben: config_local.py está en .gitignore)
cp config_local_example.py config_local.py
#   el ticket de ChileCompra va en .env:  LOVEO_CHILECOMPRA_TICKET=tu-ticket

# migración de esquema (crea adjudicaciones, items, competidores, participaciones, relicitaciones)
python schema_v2.py

# key de Anthropic para la Capa C (formato sk-ant-...):
export ANTHROPIC_API_KEY="sk-ant-..."          # Windows: setx ANTHROPIC_API_KEY "sk-ant-..."
```

---

## 2) RUTINA — cada vez que querés trabajar

### Capa A — descubrir + score (desde cualquier lado)
```bash
python run_daily.py 18062026        # fecha ddmmaaaa; sin fecha = hoy
# atrasados de golpe:
python run_daily.py --backfill 5    # los últimos 5 días hábiles que falten
```
Esto descubre candidatos, corre admisibilidad, score provisional, y **extrae adjudicaciones/items +
reconstruye competidores + enlaza re-licitaciones** (todo automático).

### Capa B — bajar las bases (LOCAL)
```bash
python download.py 2450-56-LE26     # una licitación
python download.py                  # todas las admisibles sin docs
```
- Si aparece el muro anti-bot ("actividad anormal"): poné `HEADLESS = False` en `download.py` (navegador visible).
- Si abre pero la grilla no entrega archivos: `python calibrate_ficha.py 2450-56-LE26` y mandame
  `calibration/viewattachment.html` (cierro el último selector).
- Los archivos quedan en `storage/<codigo>/`.

### Visita a terreno — se detecta al INGESTAR, no al analizar
```bash
python visitas.py 1658-171-LE26     # detecta y guarda el carácter de la visita de una licitación
python visitas.py --pendientes      # las que tienen visita detectada y siguen abiertas
python visitas.py --riesgo          # vigentes SIN bases con la ventana de visita ya corriendo
```
- `Fechas.FechaVisitaTerreno` del API viene **null siempre** (40/40 medidas): la visita está escrita
  en el pliego, no en el API. Por eso la alerta vieja de `alertas.py` nunca se disparó.
- `ingest_bases` corre la detección sola cada vez que registra documentos nuevos, y rellena las
  viejas de a poco (topes `LOVEO_VISITA_MAX_BACKFILL`=25 y `LOVEO_VISITA_MAX_SEG`=120 s por corrida,
  porque un pliego escaneado se va en OCR).
- `visita_caracter` NULL ≠ `'sin_visita'`: NULL es "todavía no se leyó el pliego", `sin_visita` es
  "se leyó y no la menciona". Las NULL con bases pendientes son las que salen en `--riesgo`.

### Capa C — leer las bases con IA (necesita ANTHROPIC_API_KEY)
```bash
# 1) primero un dry-run: estima tokens, NO gasta
python capa_c.py --pdf storage/2450-56-LE26/<archivo>.pdf --dry

# 2) extracción estructurada (presupuesto, plazos, garantías, criterios+pesos, requisitos, complejidad)
python capa_c.py --codigo 2450-56-LE26

# 3) preguntas sobre el contenido (Q&A Nivel 3)
python capa_c.py --codigo 2450-56-LE26 --pregunta "¿Qué garantía exige y a qué plazo de entrega?"
```

### Tablero — ver y decidir
```bash
streamlit run tablero3.py
```
- Secciones: Inicio · Señales · Listado · Radar · Mapa · Competitiva · Desiertas · Competencia · Asistente IA · Métricas · Keywords · Aprendizaje.
- El **feedback** (aprobar / descartar / excluir término) se hace con los botones del tablero;
  descartar con un término lo agrega a las exclusiones aprendidas y el filtro lo evita en adelante.

---

## 3) TROUBLESHOOTING

| Síntoma | Causa / solución |
|---|---|
| `run_daily` devuelve error 10500 | Rate-limit de la API. Reintenta solo (loop 4s). Con tu ticket propio casi no debería pasar. |
| `download.py` muestra "actividad anormal" | Muro anti-bot. `HEADLESS=False` y correr en IP residencial CL. |
| Capa C: "Falta ANTHROPIC_API_KEY" | Exportá la key `sk-ant-...`. Para ver costo sin gastar, usá `--dry`. |
| OCR no extrae nada | Falta el binario `tesseract-ocr-spa`. Instalalo (ver Setup). |
| Tablero con tablas vacías | Todavía no corriste `run_daily.py` con tu ticket. |

## 4) INVARIANTES (no romper)
- El **margen final** del score (GO/NO-GO) necesita la **cubicación de Valentina** — Capa C aporta el
  techo de presupuesto y la complejidad, no el costo real.
- Un **código real de Mercado Público** solo lleva su **dato real**; nada inventado en las vistas.
- La **visita a terreno se lee del pliego**, nunca del API. Una visita excluyente no detectada
  elimina la oferta sin importar precio ni capacidad técnica: en agosto de 2026 costó cinco
  licitaciones en un solo lote, una de ellas la única financieramente sana de dieciséis.
- Un **dato que falta no es un dato en cero**. Una licitación sin `fecha_cierre` no la saca ningún
  filtro y queda "vigente" para siempre; una sin bases no dice "no hay visita", dice "no sabemos".
  `run_daily` cura las dos solo (`_curar_sin_detalle` y `visitas.en_riesgo`); si agregás un filtro
  nuevo, preguntate qué hace con el NULL antes de darlo por bueno.
- Una decisión (descarte, aprobación, resultado) **no existe hasta que está en la base**. Un análisis
  que concluye "inadmisible" y no llama a `feedback.descartar()` deja la licitación viva en el
  tablero: pasó con las cinco de la visita y sólo se detectó cuando la alerta las volvió a mostrar.
- Base de datos: `loveo.db` · documentos: `storage/<codigo>/` · credenciales: `config_local.py` (no se sube).
