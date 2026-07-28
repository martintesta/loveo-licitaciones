# SPEC: Plan del día / Next-Best-Action

## Resultado ODI que ataca (por qué)

Resultado deseado subatendido: **"minimizar el tiempo y la energía que gasto decidiendo qué atacar
y en qué orden"**. Hoy el sistema INFORMA (scorea, filtra, avisa) pero no DIRIGE: el usuario mira el
tablero y decide solo qué hacer primero. La meta es que el sistema **sugiera cada vez más y mejor
qué hacer, priorizar y cómo organizar el día** — y que con el uso el usuario tenga que decidir menos.

## Requisitos

1. Componer TODAS las señales que ya existen (score × confianza, días al cierre, visita obligatoria,
   estado en el embudo, reputación del comprador, si falta la cubicación/margen, aprendizaje) en una
   **cola priorizada de ACCIONES** — no de licitaciones sueltas.
2. Cada acción trae **un porqué** legible ("terminá la cubicación de Y — cierra en 2 días, score 88")
   y una **prioridad** que pondera urgencia (deadline) y valor (score×confianza).
3. Es una recomendación, **no ejecuta nada**: el usuario decide; el sistema ordena y explica.
4. (Fases siguientes) Empujar el plan por email como "tu plan de hoy" y **aprender del
   comportamiento** (qué acepta/ignora/reordena) para mejorar el ranking.

## Diseño

- **`plan.py` (motor puro)**: `construir(lics, hoy)` toma el `lics` que ya arma `build_data` (tiene
  score, confianza, días, visita, estado, ajuste, reputación, cubicación, análisis) y devuelve una
  lista de acciones `{tipo, codigo, titulo, motivo, prioridad, dias}` ordenada. Puro → testeable sin DB.
- **Tipos de acción** (derivados de estado + señales): `VISITA` (visita obligatoria próxima),
  `PRESENTAR` (aprobada + lista + cierra pronto), `CIERRE` (en juego + cierra pronto), `CUBICAR`
  (bases leídas, falta la cubicación/margen), `REVISAR` (nueva fit sin revisar, score alto),
  `BASES` (admisible, score alto, sin bases).
- **Prioridad** = `valor` (score × confianza) + `urgencia` (por días al deadline; la visita pesa más
  que el cierre porque perderla descalifica) + `tipo` (los atados a deadline arriba). Explícita y
  ajustable por config.
- **build_data** expone `data["plan"]`; la UI muestra un panel **"PLAN DE HOY"** arriba del Inicio.
- Requiere exponer `diasVisita` (días a la visita) por lic en build_data.

## Decisiones

- **Reglas de acción explícitas y ajustables** (no un LLM opaco en la Fase 1): pesos/umbrales en
  config. La inteligencia se agrega después (aprender del comportamiento, Fase 3).
- **El plan sugiere, no actúa.** Ninguna acción se ejecuta sola; el usuario clickea e va a la ficha.
- **Solo licitaciones EN JUEGO** (no descartadas, no presentadas/cerradas).
- **Aprovecha lo que ya hay**: no recomputa nada; consume el `lics` de build_data.

## No-objetivos (por ahora)

- Ejecutar acciones por el usuario (presentar, agendar) — solo sugerir.
- Un modelo de preferencia por usuario / aprender del comportamiento (Fase 3).
- Integración con calendario (Fase futura).
