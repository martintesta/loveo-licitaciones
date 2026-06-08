# loveo-licitaciones — Capa A (descubrimiento + triage)

Herramienta de descubrimiento y triage de licitaciones públicas de Chile
(Mercado Público / ChileCompra) para **Loveo Construcciones SPA** (construcción
modular en acero). Corre a diario, acotada a la **zona sur** de Chile, porque la
empresa abre base en Puerto Montt y ahí tiene ventaja logística.

Esta es la **Capa A**: surfacing rápido de candidatas del sur a partir de la API
oficial. **No** descarga documentos (bases/anexos): la API no los entrega —
viven en la ficha web (JavaScript). Eso es la **Capa B** (futura, navegador
headless) y queda explícitamente fuera de alcance acá.

## Qué hace (el embudo)

1. **Descubre** las licitaciones publicadas en los últimos N días vía la API oficial.
2. **Filtra por keywords** sobre el nombre (barato, sin gastar llamadas de detalle).
3. Pide **detalle** solo a las que pasan el filtro (con tope configurable).
4. Filtra **zona sur** + corre **admisibilidad** + un **pre-score** de triage.
5. **Exporta** las candidatas a `outputs/` (CSV + JSON), ordenadas.

```
listar por fecha  →  filtro keyword  →  dedup  →  detalle  →  filtro sur  →  admisibilidad + prescore  →  outputs/
   (~1000/día)        (barato)                    (con tope)    (la región solo viene en el detalle)
```

## Honestidad del pre-score

Con la sola API solo se puede puntuar de forma defendible:

- **Cash flow** (modalidad de pago)
- **Logística** (región vs. base operativa)
- **Alineación** (fuerza de keywords en el nombre)

**No** se inventan margen, complejidad ni repetibilidad: eso requiere los
documentos y se delega al scoring completo (Capa B, futura). Cada fila exportada
incluye una `nota` que lo aclara.

## Instalación

```bash
pip install -r requirements.txt
```

Python 3.9+ (probado en 3.11).

## Configuración

Las **credenciales** y los **parámetros operativos** van en `.env` (gitignored).
La **calibración real** (keywords, tiers) va en `config_local.py` (gitignored).

1. Copiá `.env.example` a `.env` y poné tu ticket de ChileCompra:

   ```
   LOVEO_CHILECOMPRA_TICKET=tu-ticket-aca
   ```

   Si no ponés ticket, el sistema usa el **ticket público de PRUEBA** de
   ChileCompra (rate-limit alto, solo para arrancar). Para producción pedí el
   tuyo a api@chilecompra.cl.

2. Copiá `config_local_example.py` a `config_local.py` y ajustá la calibración
   real (keywords de Loveo, tiers de logística y cash flow).

`config.py` carga `config_local.py` si existe; si no, cae a
`config_local_example.py` y te avisa cuál cargó.

### Parámetros (env, opcionales)

| Variable                    | Default      | Qué hace                                  |
|-----------------------------|--------------|-------------------------------------------|
| `LOVEO_CHILECOMPRA_TICKET`  | ticket prueba| Ticket de la API.                         |
| `LOVEO_DIAS_HACIA_ATRAS`    | `3`          | Cuántos días hacia atrás listar.          |
| `LOVEO_MAX_DETALLES`        | `150`        | Tope de llamadas de detalle por corrida.  |
| `LOVEO_DELAY`               | `0.5`        | Delay (seg) entre llamadas a la API.      |
| `LOVEO_BASE`                | `puerto_montt`| Base operativa (override de calibración).|

## Uso

```bash
python main.py
```

Genera `outputs/candidatas_sur_AAAAMMDD_HHMM.csv` y `.json`, e imprime un
resumen de las top candidatas. El CSV se escribe en `utf-8-sig` (abre bien en
Excel con acentos).

## Tests

```bash
pytest
```

## Estructura

```
config.py                 # MECANISMO (público): credenciales desde env + carga de calibración
config_local.py           # CALIBRACIÓN REAL (privada, gitignored)
config_local_example.py   # plantilla neutra (pública)
api_client.py             # wrapper de la API con backoff de 429
filters.py                # keywords (límite de palabra), región sur, admisibilidad
prescore.py               # pre-score de triage honesto
main.py                   # orquesta el embudo y exporta a outputs/
tests/                    # pytest
```

## Seguridad

- Credenciales solo en `.env`. La calibración de negocio solo en `config_local.py`.
- Ambos están en `.gitignore`. Repo público = solo tooling genérico.
- Datos de la empresa, financieros e inversionistas **nunca** entran al repo.
