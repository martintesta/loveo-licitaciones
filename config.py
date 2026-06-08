"""
config.py — MECANISMO público (sin secretos).

Lee credenciales y parámetros operativos desde el entorno (.env) y carga la
calibración real desde `config_local.py` (privada, gitignored). Si esa no
existe, cae a `config_local_example.py` (plantilla pública neutra) y avisa cuál
cargó.

Este archivo es PÚBLICO: nunca pongas acá keywords reales, tickets reales ni
datos de la empresa. Eso vive en `.env` y en `config_local.py`.
"""
import os


def _cargar_dotenv(ruta=".env"):
    """Carga pares CLAVE=VALOR de un archivo .env al entorno, sin dependencias.

    No sobrescribe variables que ya estén presentes en el entorno (el entorno
    real manda sobre el archivo).
    """
    if not os.path.exists(ruta):
        return
    # utf-8-sig: tolera el BOM que agregan Notepad/PowerShell al guardar.
    with open(ruta, encoding="utf-8-sig") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, _, valor = linea.partition("=")
            clave = clave.strip()
            valor = valor.strip().strip('"').strip("'")
            if clave:
                os.environ.setdefault(clave, valor)


_cargar_dotenv()

# --- Ticket / credenciales -------------------------------------------------
# Ticket PÚBLICO DE PRUEBA de ChileCompra (rate-limit alto). SOLO para que el
# proyecto arranque sin configurar nada. NO es un ticket real de producción y
# NUNCA debe hardcodearse uno real acá: el real va en .env.
TICKET_PUBLICO_PRUEBA = "F8537A18-6766-4DEF-9E59-426B4FEE2844"

TICKET = os.environ.get("LOVEO_CHILECOMPRA_TICKET") or TICKET_PUBLICO_PRUEBA
USANDO_TICKET_PRUEBA = TICKET == TICKET_PUBLICO_PRUEBA

# --- Parámetros operativos del embudo --------------------------------------
DIAS_HACIA_ATRAS = int(os.environ.get("LOVEO_DIAS_HACIA_ATRAS", "3"))
MAX_DETALLES = int(os.environ.get("LOVEO_MAX_DETALLES", "150"))
DELAY = float(os.environ.get("LOVEO_DELAY", "0.5"))

# --- Calibración (privada si existe, ejemplo si no) ------------------------
try:
    from config_local import *  # noqa: F401,F403
    CALIBRACION_CARGADA = "config_local.py (calibración privada)"
except ImportError:
    from config_local_example import *  # noqa: F401,F403
    CALIBRACION_CARGADA = "config_local_example.py (plantilla pública neutra)"

# BASE_OPERATIVA puede forzarse por entorno (override de la calibración).
BASE_OPERATIVA = os.environ.get("LOVEO_BASE", BASE_OPERATIVA)  # noqa: F405

# Aviso al importar: qué calibración quedó activa (sin exponer el ticket).
print(f"[config] Calibración cargada: {CALIBRACION_CARGADA}")
