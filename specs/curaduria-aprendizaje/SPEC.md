# SPEC: curaduría manual + aprendizaje de descartes

## Problema
1. El descubrimiento solo trae lo que matchea keywords. Si una licitación buena no matcheó,
   no hay forma de meterla a mano → se pierde.
2. Cuando descarto, el "por qué" se guarda como texto libre y NO mejora el scoring. El sistema
   no aprende de mis decisiones; repite las mismas sugerencias malas.

## Objetivo
1. Agregar cualquier licitación por su código MP, saltándose el filtro.
2. Capturar el motivo de descarte de forma estructurada y usarlo para ajustar el score
   futuro de licitaciones parecidas — de forma EXPLÍCITA y reversible (modo asistido).

## Alcance
- Incluye: alta manual por código; descarte con categoría; tabla `descartes`; panel de patrones;
  ajuste asistido del score con razón visible.
- NO incluye: ML/caja negra, auto-descartar sin mostrar, scraping fuera de la API oficial.

## Criterios de aceptación (exit 0 = pasa)
- [ ] Alta manual inserta la lic con score y evento 'agregada_manual' -> `python -m pytest tests/test_manual_add.py -q`
- [ ] Descarte estructurado guarda categoría en `descartes` -> `python -m pytest tests/test_aprendizaje.py -q`
- [ ] El ajuste asistido nunca es silencioso (siempre trae razón) -> test del módulo `aprendizaje`
- [ ] Sin regresiones -> `python scripts/preflight.py`

## Invariantes a respetar
- Score PROVISIONAL; el ajuste es un delta EXPLÍCITO sobre el provisional, con su nota, reversible.
- Nada inventado: el ajuste se basa solo en descartes reales que el usuario hizo.
- Shim Postgres (lastrowid/SUM), secretos en .env (ver CLAUDE.md).

## Decisión tomada
Modo **asistido**: muestra patrones + aplica ajuste suave y explícito (ej. -8 con nota
"descartaste 4 similares por muy lejos"), siempre visible y deshacible.

## Riesgos / decisiones abiertas
- Definir el umbral de "patrón" (¿desde cuántos descartes similares se dispara el ajuste?). Default: 3.
- Evitar esconder oportunidades: el ajuste se muestra como nota, no borra la lic del listado.
