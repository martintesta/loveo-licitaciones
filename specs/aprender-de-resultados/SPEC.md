# SPEC: aprender de resultados + score honesto

Ataca 3 deudas de concepto relacionadas (#4, #2, #1 de la auditoría):

## Problema
1. El sistema aprende de por qué **descartamos**, pero NO de los **resultados** (ganada/perdida)
   — que son la señal más fuerte. Hoy marcar una ganada/perdida no enseña nada.
2. El score provisional **se ve más seguro de lo que es**: margen (×3) y complejidad (×2) quedan
   siempre en neutro hasta la cubicación, pero el número (ej. "74") se lee como final.

## Objetivo
1. Capturar **por qué ganamos/perdimos** (motivo estructurado, como las categorías de descarte).
2. Que el aprendizaje **sume las victorias** como señal positiva y trate las **pérdidas según su
   motivo** — con peso por confianza (cantidad) y sin castigar buenas oportunidades.
3. Mostrar la **confianza del score**: cuántas dimensiones están realmente evaluadas.

## Alcance
- Incluye: motivo estructurado en resultado; aprendizaje bidireccional (victorias +, pérdidas
  según motivo); indicador de confianza del score en lista y ficha.
- NO incluye: modelo de probabilidad de ganar (#6 — necesita historial, lo habilita ESTE epic con
  el tiempo), multi-tenancy (#7), scraping de pago real (#5, CAPTCHA), auto-cubicación (#8, diseño).

## Criterios de aceptación (exit 0 = pasa)
- [ ] Marcar ganada/perdida pide y guarda motivo estructurado -> `pytest tests/test_resultados.py`
- [ ] Victorias suben / pérdidas ajustan el score de parecidas según motivo -> test de aprendizaje
- [ ] El score muestra su confianza (N/6 dims, evaluable_pts) en build_data y UI -> tests
- [ ] Sin regresiones -> `python scripts/preflight.py`

## Invariantes
- Score PROVISIONAL; los ajustes son EXPLÍCITOS y reversibles (display-only, no mutan el score base).
- Operativo nunca penaliza (ya). Nada inventado: solo resultados/descartes reales.
- Peso por confianza: 3 datos no pesan como 30; patrones viejos deberían decaer (v1: al menos peso por N).

## Decisión de producto (Fase B) — cómo una PÉRDIDA afecta el score
**Según el motivo.** Las pérdidas ESTRUCTURALES (no cumplíamos un requisito, plazo imposible,
"no era para nosotros" = mal_fit) BAJAN el score de parecidas. Las pérdidas COMPETITIVAS
(perdimos por precio, competencia fuerte) NO tocan el score — era buena, la perdiste compitiendo;
se registran como 'competida'. Las victorias suman señal positiva. Mapeo de impacto por categoría:
- ganada (todas) -> `positivo`
- perdida: requisito / plazo / mal_fit -> `malfit` (baja) · precio / competencia_fuerte -> `competida` (no toca) · otro -> `neutro`

## Riesgos
- Loop de confirmación: el ajuste no debe entrenar un sesgo que esconda oportunidades. Por eso
  display-only + explícito + reversible, y las pérdidas por competencia no bajan el fit.
