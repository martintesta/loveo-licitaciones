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


# --- Calibración OPCIONAL (descomentá en tu config_local.py para sobreescribir los defaults) ---

# Distancias reales por carretera (km) desde cada base, por región normalizada (sin acentos,
# minúsculas). Reemplaza las APROXIMACIONES de scoring.py:BASES con tus números reales.
# BASES_DISTANCIAS = {
#     "Pirque":       {"metropolitana": 30, "maule": 250, "los lagos": 1000},
#     "Puerto Montt": {"los lagos": 30, "araucania": 350, "metropolitana": 1000},
# }

# Aprendizaje de descartes (aprendizaje.py): cuándo y cuánto ajusta el score.
# APRENDIZAJE_UMBRAL = 3   # descartes parecidos para disparar el ajuste
# APRENDIZAJE_PENAL = {"muy_lejos": 6, "mal_pagador": 8, "requisito_excluyente": 8}  # baja sobre 120
