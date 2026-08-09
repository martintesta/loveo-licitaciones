# SPEC: precios-al-dia

## Problema

El costo es la mitad del GO/NO-GO. El catálogo tenía 91 precios reales del proyecto Talagante
cargados una vez (junio 2026) y nada que los mantuviera vivos: a los seis meses el margen que
muestra el análisis es ficción, y nadie se entera porque el número igual aparece.

Faltaban tres cosas: refrescarlos solos cada tanto, poder corregir uno a mano cuando llega una
cotización firme, y poder auditar de dónde salió cada precio.

## Objetivo

Que el catálogo de precios se mantenga al día solo, acepte correcciones manuales, y que cada precio
sea auditable: cuándo se tomó y de qué link salió.

## Decisiones

1. **Append-only, nunca UPDATE.** Cada cotización es un punto nuevo con fecha *y hora*, así conviven
   varios precios del mismo material y se ve la tendencia. El "precio vigente" es el último punto.
   La hora importa: sin ella dos cotizaciones del mismo día no se pueden ordenar.
2. **Todo precio guarda su origen**: `fuente` (valentina / web / manual / interno) y `source_url`
   con el link de la página que mostraba ese precio. Un precio sin trazabilidad no se puede auditar.
3. **Mensual, y solo lo vencido.** Re-cotizar los 91 materiales todos los meses es quemar búsquedas
   para reconfirmar lo que ya sabíamos. Un precio de mercado vence a los 45 días; uno que es un
   HECHO (lo que Loveo pagó, o una corrección de Martín) aguanta 180 — no es una estimación.
4. **La corrección manual manda.** Si Martín corrige un precio, el job mensual no se lo pisa a la
   semana siguiente.
5. **Una sola fuente de búsqueda.** `precios.buscar_precio_web` es la única cotizadora del proyecto;
   `cubicacion_ia` delega ahí. Si divergieran, el precio que se guarda al preciar un BOM y el del
   refresco mensual saldrían de prompts distintos.

## Alcance

- **Incluye**: `precios.py` (refrescar / corregir / registrar / historial / vencidos / catalogo),
  CLI, y la tarea programada mensual de Windows.
- **NO incluye**: botón de corrección en el tablero (hoy es por CLI) · scraping directo de
  proveedores (se usa web search) · precios por región o por proveedor (el esquema los soporta,
  la lógica todavía no los distingue).

## Criterios de aceptación

- [x] Un precio nuevo no pisa al anterior y ambos conviven con fecha y hora
      → `python -m pytest tests/test_precios.py -q`
- [x] El precio web guarda el link de donde salió → mismo comando
- [x] El refresco solo toca lo vencido, y respeta las correcciones manuales → mismo comando
- [x] Si la búsqueda falla, el precio viejo sigue vigente (nunca dejar un material sin precio)
- [x] La tarea mensual queda registrada y corre → `schtasks /Run /TN LoveoPrecios` + `logs\tarea_precios.log`
- [x] Sin regresiones → `python scripts/preflight.py`

## Invariantes respetados

- **No inventar**: si la web no encuentra precio, no se escribe nada y el punto viejo sigue siendo
  el vigente; el material queda reportado en el resumen del job.
- **Postgres vs SQLite**: todo por `db.conn()`; el id nuevo se re-SELECTea, sin `lastrowid`.
- **Secretos**: la API key sale del entorno o `config_local`.

## Riesgos / decisiones abiertas

- **La corrección manual es por CLI.** Alcanza para Martín, pero el lugar natural es un botón en la
  ficha, al lado del precio. Queda como siguiente paso.
- **Colisiones de normalización**: dos descripciones distintas pueden normalizar a la misma clave y
  compartir historial. Hoy es deseable (variantes del mismo material); si molesta, hay que separar
  por `unidad` además de por `descripcion_norm`.
- **Costo del job**: una búsqueda web por material vencido. Acotado con `--limite` si hiciera falta.
