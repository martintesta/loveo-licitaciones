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
- Estado: [ ] pendiente.

## Fase 3 — Precios con referencia clickeable
- Entregable: `cubicacion_ia.preciar` — match contra `precios_referencia` (interno) + búsqueda web
  para los huecos, guardando `precio + source_url` (columna nueva). La ficha muestra cada precio con
  su fuente clickeable.
- Listo cuando: un BOM queda preciado con al menos la fuente por item; tests con búsqueda mockeada.
- Estado: [ ] pendiente. **Bloqueada por la decisión de precios web (ver SPEC).**

## Fase 4 — Margen real → score
- Entregable: costo = suma del BOM preciado; margen = techo de presupuesto − costo; actualiza la
  dimensión `margen` del `score_json` (display, reversible), con la confianza correspondiente
  (la dimensión pasa a evaluada).
- Listo cuando: una lic con cubicación preciada muestra margen y sube su confianza a 6/6; tests.
- Estado: [ ] pendiente.

## Fase 5 — Recetas por tipo de producto (la inteligencia que acelera)
- Entregable: cada cubicación curada se guarda como receta por tipo de producto; una lic nueva
  parecida pre-llena el BOM desde la receta. Métrica: cuánto encoge la curación (ítems tocados)
  proyecto a proyecto.
- Listo cuando: una segunda lic del mismo tipo arranca con el BOM pre-lleno de la receta; tests.
- Estado: [ ] pendiente.
