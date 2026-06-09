"""
config_local_example.py — plantilla pública NEUTRA de la calibración.

Copiá este archivo a `config_local.py` y reemplazá con la calibración real de la
empresa. Mantiene la MISMA estructura que `config_local.py` pero con valores de
ejemplo. Este archivo SÍ es público; `config_local.py` NO.
"""

KEYWORDS_INCLUIR = ["container", "modular"]

KEYWORDS_EXCLUIR = ["palabra excluida de ejemplo"]

# Red ANCHA de recall (M-3): términos laxos para una cola de revisión.
KEYWORDS_AMPLIO = ["posta", "policlinico"]

REGIONES_SUR = ["los rios", "araucania", "los lagos", "aysen", "magallanes"]

BASE_OPERATIVA = "puerto_montt"

LOGISTICA_TIER = {
    "puerto_montt": {"los lagos": 1, "los rios": 2, "araucania": 2, "aysen": 3, "magallanes": 3},
}

CASHFLOW_TIER = {1: 1, 2: 2, 3: 3}
