# SPEC: Cubicación asistida → margen real

## Resultado ODI que ataca (por qué)

Resultados deseados subatendidos del job "evaluar si una licitación conviene":
- **Minimizar la dependencia de un tercero para conocer el margen.** Hoy el margen real sale de la
  cubicación en Excel de Valentina (`cubicacion.py:ingest`, `origen='valentina'`). Sin ese Excel, el
  score se queda provisional (margen = neutro 5).
- **Maximizar la confianza en el número que decide.** La dimensión `margen` (peso ×3, la más pesada)
  nunca está evaluada hasta que llega la cubicación.

Meta: que el sistema **arme la cubicación solo desde las bases**, la **precie con referencia
clickeable**, y **aprenda recetas** por tipo de producto para que la curación se achique proyecto a
proyecto — hasta cerrar el margen del score sin depender de un tercero.

## Requisitos

1. Desde las bases (generales + técnicas), la IA arma un **borrador de listado de materiales (BOM)**:
   partidas con grupo (material / mano de obra / transporte / otros), descripción, cantidad estimada
   y unidad.
2. El usuario **cura** el borrador (edita cantidades, agrega/saca partidas). Es un **borrador para
   curar, no una cotización** — se comunica así en la UI.
3. Cada partida se **precia**: primero el catálogo interno (`precios_referencia`), y para los huecos
   una **búsqueda web** que trae un precio con la **URL del ecommerce** de donde salió (clickeable).
   No importa que sea el más barato; importa que sea **trazable**.
4. El BOM preciado → **costo estimado** → comparado con el techo de presupuesto (Capa C) → **margen
   real**, que alimenta la dimensión `margen` del score (deja de ser neutro).
5. Cada cubicación curada se guarda como **receta** por tipo de producto; la próxima licitación
   parecida se **pre-llena** desde la receta y el usuario solo ajusta las diferencias. Se puede
   medir cuánto encoge la curación con el tiempo.

## Diseño (se apoya en lo que ya existe)

- **Tablas** (`schema_v3`): reusar `cubicaciones` (nuevo `origen='ia'`) + `cubicacion_items`
  (partida/grupo/descripcion/cantidad/unidad/precio_unitario/total). Fase 2 agrega `source_url` a
  `precios_referencia` (hoy tiene `fuente` que ya admite `'web'`, falta la URL clickeable).
- **Extracción**: extender el prompt de `capa_c.py` para producir `materiales` (lista de
  {partida, grupo, descripcion, cantidad, unidad}) junto a lo que ya extrae.
- **Almacenamiento**: un módulo `cubicacion_ia.py` toma la extracción y persiste el BOM como una
  `cubicaciones(origen='ia')` + sus `cubicacion_items`. Idempotente por (codigo, origen='ia').
- **Curación**: UI en la ficha para ver y editar los items (round-trip suave, como el resto de
  acciones del tablero).
- **Precios** (Fase 2): `cubicacion_ia.preciar(items)` — match contra `precios_referencia` por
  `descripcion_norm`; para los huecos, búsqueda web → precio + `source_url`, cacheado en
  `precios_referencia(fuente='web')` para enriquecer el catálogo propio.
- **Margen** (Fase 3): igual que `capac_score` con complejidad — `cubicacion_ia` calcula el costo y
  actualiza la dimensión `margen` del `score_json` (display, reversible, con trazabilidad).

## Decisiones

- **[RESUELTA] Cómo traer los precios web.** Se optó por **catálogo interno primero + búsqueda web
  para los huecos**, guardando `source_url` clickeable. El mecanismo de búsqueda vive detrás de un
  punto pluggable (`cubicacion_ia._buscar_web_real`, hoy Claude web search) e inyectable — se puede
  cambiar por una API de búsqueda o scraping sin tocar el orquestador. Apagable con
  `LOVEO_PRECIOS_WEB=0`. No importa el más barato: importa la referencia trazable.
- **Calidad = borrador asistido, NO cotización.** Explícito en la UI. El valor está en el arranque +
  el aprendizaje, no en exactitud al peso.
- **El ajuste al score es display-only y reversible** (como el resto): el margen real actualiza la
  dimensión en `score_json`, sin inventar nada; si no hay cubicación, queda el neutro honesto.
- **La cubicación de Valentina (Excel) sigue siendo válida y prioritaria**: si existe una
  `origen='valentina'` para el código, esa manda sobre la `origen='ia'`. La IA no la pisa.

## No-objetivos (por ahora)

- Encontrar el precio más barato (solo referencia trazable).
- Reemplazar el criterio humano: la cubicación IA es un borrador que el usuario aprueba.
- Cotización legal/exacta para presentar; es para el GO/NO-GO interno.
