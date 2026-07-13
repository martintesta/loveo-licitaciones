# PHASES: cubicación asistida → margen real

## Fase 1 — BOM asistido desde las bases (el borrador)
- Entregable: extender la Capa C para extraer `materiales` (BOM) de las bases; `cubicacion_ia.generar`
  persiste el borrador como `cubicaciones(origen='ia')` + `cubicacion_items`. La ficha muestra el
  borrador (con el aviso "borrador para curar, no cotización"). Respeta la cubicación de Valentina si
  existe (no la pisa).
- Listo cuando: analizar una lic deja un borrador de cubicación consultable; `cubicacion_ia.generar`
  es idempotente por (codigo, origen='ia'); tests con extracción mockeada (sin gastar tokens).
- Estado: [x] hecho. `capa_c` extrae `materiales`; `cubicacion_ia.generar/borrador` persisten el
  borrador en cubicaciones(origen='ia')+cubicacion_items (idempotente, respeta 'valentina').
  build_data expone `cubicIA`; ficha muestra el borrador + botón generar/regenerar. 7 tests.

## Fase 2 — Curación (editar el borrador)
- Entregable: UI en la ficha para editar cantidades, agregar/quitar partidas y aprobar. La curación
  es lo que después alimenta las recetas (Fase 4).
- Listo cuando: el usuario edita un item y el cambio persiste (round-trip); tests.
- Estado: [x] hecho. `cubicacion_ia.guardar_borrador(codigo, items)` reemplaza el borrador con la
  lista curada (normaliza, descarta filas vacías, crea si no existía, respeta 'valentina'). UI:
  filas con inputs editables + agregar/quitar (client-side) + "Guardar curación" (bulk-save).
  Persistido refactorizado a `_reemplazar_items` (compartido con generar). +4 tests.

## Fase 3 — Precios con referencia clickeable
- Entregable: `cubicacion_ia.preciar` — match contra `precios_referencia` (interno) + búsqueda web
  para los huecos, guardando `precio + source_url` (columna nueva). La ficha muestra cada precio con
  su fuente clickeable.
- Listo cuando: un BOM queda preciado con al menos la fuente por item; tests con búsqueda mockeada.
- Estado: [x] hecho. `cubicacion_ia.preciar(codigo, buscar=None)` — catálogo interno primero
  (match por descripcion_norm) y búsqueda web para los huecos (source_url clickeable), cacheando el
  precio web en precios_referencia. Columnas nuevas: cubicacion_items(precio_fuente, precio_url),
  precios_referencia(source_url), con ALTER idempotente. `_precio_num` tolera formato CLP. UI:
  precio + 🔗 fuente por partida + subtotal + botón "Preciar". Web pluggable/inyectable, apagable
  con LOVEO_PRECIOS_WEB=0. 8 tests.

## Fase 4 — Margen real → score
- Entregable: costo = suma del BOM preciado; margen = techo de presupuesto − costo; actualiza la
  dimensión `margen` del `score_json` (display, reversible), con la confianza correspondiente
  (la dimensión pasa a evaluada).
- Listo cuando: una lic con cubicación preciada muestra margen y sube su confianza a 6/6; tests.
- Estado: [x] hecho. `cubicacion_ia.margen(codigo)` = costo (BOM preciado) vs techo (Capa C) →
  margen + %. Aplica a la dimensión `margen` del score (evaluada, tramos `_score_margen`
  configurables) SOLO si todo está preciado (si faltan, muestra el estimado sin tocar el score →
  honesto). Guarda costo/margen en la cubicación. UI: botón "Calcular margen → score". +6 tests.

## Fase 5 — Recetas por tipo de producto (la inteligencia que acelera)
- Entregable: cada cubicación curada se guarda como receta por tipo de producto; una lic nueva
  parecida pre-llena el BOM desde la receta. Métrica: cuánto encoge la curación (ítems tocados)
  proyecto a proyecto.
- Listo cuando: una segunda lic del mismo tipo arranca con el BOM pre-lleno de la receta; tests.
- Estado: [x] hecho. `tipo_producto(nombre)` clasifica; `guardar_borrador` alimenta la receta del
  tipo (cubicaciones origen='receta', proyecto=tipo) en cada curación; `prellenar_desde_receta`
  arranca una lic parecida con el BOM de la receta (sin IA). build_data expone `recetaDisp`; UI
  ofrece "Pre-llenar desde receta" cuando no hay borrador y hay receta. 8 tests.

## Epic COMPLETO (fases 1–5). El objetivo central —cubicar desde las bases, curar, preciar con
## referencia clickeable, cerrar el margen del score y aprender recetas— está cumplido, sin depender
## de la cubicación de un tercero. Deuda futura: métrica de "cuánto encoge la curación" proyecto a
## proyecto; recetas por sub-tipo/tamaño; sugerir precios de la receta al pre-llenar.
