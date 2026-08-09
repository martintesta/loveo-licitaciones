# Desafío al modelo de scoring de licitaciones — Loveo Construcciones

> Documento autocontenido para pegar en Claude, Gemini o cualquier otro modelo.
> No hace falta ningún archivo adjunto: todo lo necesario está acá.

---

## Tu rol

Sos un consultor senior en toma de decisiones bajo incertidumbre, con experiencia en compras
públicas y en diseño de sistemas de scoring. Te contrato para **destruir** el modelo que sigue,
no para validarlo. Si el modelo está mal, quiero saber exactamente dónde y qué lo reemplaza.
Si algo está bien, decilo también, pero no me hagas la pelota.

Sé concreto y numérico. Prefiero una crítica dura y accionable a una lista de buenas prácticas.

---

## El negocio

**Loveo Construcciones SpA** es una empresa chilena que fabrica **construcción modular en acero**:
contenedores marítimos acondicionados como oficinas, salas clínicas, box dentales, salas de
residuos hospitalarios (REAS/RESPEL), baños y camarines modulares. Vende casi exclusivamente al
Estado, vía licitaciones de **Mercado Público** (el portal de compras públicas de Chile).

Datos económicos relevantes:

- Base operativa: **Puerto Montt** (sur de Chile). Hay una segunda base en Pirque (Santiago).
- **Sobrecosto real medido: 30%** sobre el costo directo cubicado (no 20%, se midió).
- **Margen mínimo aceptable: 25%. Objetivo: 35-40%.**
- El financiamiento es **por proyecto**, no por tiempo: capital adelantado × 10%, una sola vez.
- **Estructura fija mensual: CLP 17.800.000.** Todo proyecto se juzga contra ese número.
- Proyectos a **más de 300 km** de la base se penalizan: el flete destruye el margen.
- De esas reglas sale un techo de costo: para margen SANO, el costo base debe ser
  ≤ techo_neto / 1,885. Para el límite absoluto, ≤ techo_neto / 1,625.

El volumen es de unas **200 licitaciones detectadas por trimestre**, de las cuales Loveo puede
analizar en profundidad quizá 15-20. **El scoring existe para decidir a cuáles dedicarles tiempo.**

---

## El modelo actual, en detalle

Se llama "score provisional". Corre automáticamente sobre cada licitación nueva, usando
**solamente** lo que devuelve la API de Mercado Público (nombre, organismo, región, comuna,
modalidad de pago, monto estimado, fechas). **No lee las bases de licitación**, porque las bases
son PDFs protegidos con reCAPTCHA que hay que descargar a mano.

### Seis dimensiones, con peso

| Dimensión | Peso | Cómo se calcula |
|---|---:|---|
| Margen potencial | ×3 | **No se calcula.** Se fija en 5/10 y se marca "no evaluado" |
| Cash flow | ×3 | Del código de modalidad de pago de la API → tier 1/2/3 → 8/6/3 puntos |
| Complejidad técnica | ×2 | **No se calcula.** Se fija en 5/10 y se marca "no evaluado" |
| Riesgo logístico | ×2 | Distancia por región a la base más cercana, de una tabla fija |
| Alineación | ×1 | Match de palabras clave **sobre el nombre** de la licitación |
| Repetibilidad | ×1 | Match de palabras clave sobre el nombre |

Cada dimensión da 0-10. Suma ponderada, máximo teórico 120.

### Detalle de cada regla

**Logístico** (×2): tabla fija de km por región desde Pirque y desde Puerto Montt; se toma la base
más cercana. Luego: ≤100 km → 9 · ≤300 km → 7 · ≤600 km → 4 · ≤1000 km → 2 · >1000 km → 1.
El propio código dice "aprox., calibrar".

**Alineación** (×1): si el **nombre** contiene alguna de
`container, conteiner, contenedor, box dental, box veterinari, módulo, modulo, modular,
baño modular, sala, reas, respel, suspel` → 9.
Si contiene `paradero, garita, panel solar, carpa` → 6. Si no → 4.

**Repetibilidad** (×1): si el nombre tiene una palabra modular y **no** tiene una de
`mejoramiento, remodelación, mantención, habilitación, reparación, ampliación` → 8.
Si tiene una de esas → 3. Si no → 5.

**Cash flow** (×3): del campo `Modalidad` de la API (1=pago a 30 días, 6=contra entrega,
8=por estado de avance, etc.) mapeado a tier 1/2/3, que da 8/6/3 puntos. Si el campo viene
vacío → 5 y se marca no evaluado.

### Umbrales de triage

- **≥ 85** → "Priorizar"
- **≥ 60** → "Revisar"
- **< 60** → "Descartar candidato"

---

## Lo que el modelo NO mira

- **El monto de la licitación.** Verificado: la palabra "monto" no aparece en el módulo de scoring.
  Una licitación de CLP 450.000.000 y una de CLP 10.000 pueden puntuar exactamente igual.
- La descripción del objeto (solo mira el título).
- El rubro/categoría ONU del ítem, **que la API sí entrega** (ej. 30201800 = Estructuras
  prefabricadas).
- El comprador y su historial de pago.
- Los criterios de evaluación de la licitación (cuánto pesa el precio vs. lo técnico).
- Condiciones eliminatorias: visita a terreno obligatoria, prohibición de subcontratar,
  criterios de "desarrollo local" que dan 0 puntos a un oferente de otra región.
- Si el techo de presupuesto alcanza siquiera para cubrir el costo.

---

## Evidencia empírica de cómo se comporta

Sobre **186 licitaciones puntuadas** en la base real:

| Hecho medido | Valor |
|---|---|
| Score mínimo observado | **53** |
| Score máximo observado | **84** |
| Clasificadas como "Revisar" (60-84) | **184 de 186 (98,9%)** |
| Clasificadas como "Priorizar" (≥85) | **0** |
| Licitaciones con resultado registrado (ganada/perdida) | **0** |

Aritmética del rango teórico, calculada de las reglas de arriba:

- Puntos **fijos** por las dos dimensiones no evaluadas: 5×3 + 5×2 = **25 puntos siempre**.
- Score mínimo posible: **43**. Score máximo posible: **84**.
- El umbral de "Priorizar" es **85**.

### Falsos positivos reales de esta semana

| Licitación | Score | Qué era en realidad |
|---|---:|---|
| "Desarrollo de la plataforma modular de compras" | **84** | Software para el Estado |
| "7 juegos modulares para espacios públicos" | **84** | Juegos infantiles de plaza |
| "Adquisición de contenedores refrigerados" | 68 | Equipo frigorífico, no obra |
| "Contenedor open top para camión con polibrazo" | 76 | Carrocería de camión |
| "Módulo nutricional en polvo" | (alto) | Leche en polvo |

De 16 licitaciones que se analizaron a fondo, **8 resultaron no ser el producto de Loveo.**

### Qué decidió de verdad las decisiones esta semana

Se cerraron 33 licitaciones. Los motivos reales:

| Motivo | Cantidad | ¿Estaba en el score? |
|---|---:|---|
| Fuera del negocio de Loveo | 16 | No (el score las puntuaba 68-84) |
| El costo base supera el techo del presupuesto | 9 | No (el score no mira el monto) |
| No fuimos a la visita a terreno obligatoria | 7 | No (el score no sabe de visitas) |
| Otro | 1 | — |

---

## Lo que quiero que hagas

Respondé estas preguntas, en orden, con argumentos y números:

1. **¿El umbral de 85 es alcanzable?** Verificá la aritmética vos mismo con las reglas de arriba.
   Si no lo es, ¿qué dice eso sobre cómo se diseñó y se probó este sistema?

2. **¿Tiene sentido rellenar con 5/10 las dimensiones que no se pueden evaluar?** Son 5 de 12
   unidades de peso, el 42% del modelo. ¿Cuál es la alternativa correcta: excluirlas del
   denominador, propagar incertidumbre, o algo mejor?

3. **¿Es una suma ponderada la forma correcta para este problema?** Considerá que los motivos
   reales de descarte son en su mayoría **binarios y eliminatorios** (no es nuestro producto /
   no fuimos a la visita / el techo no cubre el costo), no graduales. Argumentá a favor o en
   contra de reemplazarlo por un embudo de filtros duros seguido de un ranking.

4. **El modelo no usa el monto.** ¿Es un error o es defendible? Si hay que meterlo, ¿cómo, sin
   que una licitación grande y mala le gane a una chica y buena?

5. **Calibración.** No hay ni un solo resultado histórico registrado (0 ganadas/perdidas en la
   base). ¿Cuántos datos hacen falta para calibrar seis pesos, y qué se puede hacer mientras
   tanto? ¿Sirve de algo un modelo cuyos pesos nunca se contrastaron contra la realidad?

6. **¿Qué debería predecir el score?** Hoy es un índice de opinión. ¿Convendría que estimara algo
   falsable — probabilidad de ganar, margen esperado, valor esperado — y por qué?

7. **Rediseñalo.** Dame el modelo que vos usarías, con sus reglas concretas, qué dato necesita
   cada una, y en qué orden implementarlas para que la primera versión ya sirva.

8. **¿Qué me estoy perdiendo?** Nombrá el problema que no está en esta lista y que vos ves.

---

## Restricciones para tu propuesta

- La API de Mercado Público entrega: nombre, descripción, organismo, región, comuna, monto
  estimado (a veces null), modalidad de pago, fechas, categoría ONU del ítem, y estado.
- Las bases (PDF) sólo se consiguen descargándolas a mano; leerlas cuesta tiempo humano y
  tokens de un LLM. Cualquier regla que las requiera va **después** del filtro, no antes.
- Un falso negativo (descartar una buena) cuesta una licitación perdida.
  Un falso positivo (analizar una mala) cuesta entre 2 y 6 horas de trabajo.
  Asumí esa asimetría explícitamente en tu diseño y decime qué tasa de cada una tolerarías.
