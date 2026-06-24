"""
discover.py — Capa A: descubrimiento vía API oficial de ChileCompra (VERIFICADO EN VIVO).

Probado el 2026-06-14 contra api.mercadopublico.cl:
  - GET licitaciones.json?fecha=ddmmaaaa  -> 1.186 licitaciones del día (lista liviana)
  - GET licitaciones.json?codigo=XXXX      -> detalle completo (comprador, ítems, montos,
    fechas, prohibición de subcontratación, bloque Adjudicación con el competidor)
  - CONFIRMADO: el detalle NO trae los archivos adjuntos. Eso es Capa B (navegador).
  - El ticket de PRUEBAS está rate-limited (429 frecuente). Con ticket propio se resuelve.
    Pedí el tuyo en: https://api.mercadopublico.cl/modules/Participa.aspx

Uso:
    from discover import correr_dia
    correr_dia("11062026")            # descubre, filtra, trae detalle de los que matchean, persiste
"""

import re
import time
import json
import unicodedata
import requests

import db

# ---- Configuración: en producción, mové TICKET y las keywords a config_local.py (gitignored) ----
try:
    from config_local import TICKET, KEYWORDS, EXCLUSIONES
except ImportError:
    TICKET = "F8537A18-6766-4DEF-9E59-426B4FEE2844"  # ticket PÚBLICO de pruebas (rate-limited)
    KEYWORDS = [
        "container", "conteiner", "contenedor", "box dental", "box veterinari",
        "baño modular", "baños modulares", "sala modular", "salas dentales",
        "modulo", "módulo", "modular", "reas", "respel", "suspel",
        "garita", "paradero", "panel solar", "paneles solares", "cámara de proceso",
    ]
    EXCLUSIONES = [
        "aashto", "hs20", "viga", "puente", "arco sumergido", "certificación de soldadores",
        "vehiculo", "vehículo", "automotriz", "bodega reciclada", "container sin tratamiento",
        "laboratorio dental", "área verde", "areas verdes", "jardineria", "jardinería",
        "herramienta",  # evita "MODULAR CON HERRAMIENTAS" (falso positivo visto en vivo)
    ]

BASE = "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json"

# Match por LÍMITE DE PALABRA, INSENSIBLE A ACENTOS y tolerante a PLURAL (s/es):
#   'modulo' matchea 'modulo', 'modulos', 'módulo', 'módulos'; 'container' -> 'containers'.
#   El sufijo (?:e?s)? agrega s/es opcional; el \b final evita matchear 'boxeo' con 'box'.
def _na(s: str) -> str:
    """Normaliza: sin acentos, minúsculas."""
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()

def _pat(term: str):
    return re.compile(r"\b" + re.escape(_na(term)) + r"(?:e?s)?\b")

_KW_RE = [_pat(k) for k in KEYWORDS]
_EX_RE = [_pat(e) for e in EXCLUSIONES]

# Exclusiones aprendidas por el loop de feedback (feedback.py las agrega).
_LEARNED_FILE = __import__("pathlib").Path(__file__).parent / "exclusiones_aprendidas.txt"
def _cargar_aprendidas():
    if _LEARNED_FILE.exists():
        terms = [t.strip() for t in _LEARNED_FILE.read_text(encoding="utf-8").splitlines() if t.strip() and not t.startswith("#")]
        return [_pat(t) for t in terms]
    return []


def _get(params, tries=6, base_wait=5):
    """GET con backoff para sobrevivir el 429 del ticket de pruebas."""
    last = None
    for i in range(tries):
        r = requests.get(BASE, params=params, timeout=60)
        if r.status_code == 200 and r.text.strip().startswith("{"):
            return r.json()
        last = r.status_code
        time.sleep(base_wait * (i + 1))
    raise RuntimeError(f"API no respondió 200 tras {tries} intentos (último status={last}). "
                       f"Probable rate-limit: usá ticket propio.")


_PATRONES_CACHE = None


def _patrones():
    """Patrones (incluir, excluir) desde la tabla `keywords` (fuente de verdad); fallback a las estáticas."""
    global _PATRONES_CACHE
    if _PATRONES_CACHE is not None:
        return _PATRONES_CACHE
    try:
        import keywords as kwmod
        inc, exc, _ = kwmod.get_active_lists()
        if inc or exc:
            _PATRONES_CACHE = ([_pat(k) for k in inc], [_pat(e) for e in exc])
            return _PATRONES_CACHE
    except Exception:
        pass
    _PATRONES_CACHE = (_KW_RE, _EX_RE)  # fallback: config_local / hardcoded
    return _PATRONES_CACHE


def matchea(nombre: str) -> bool:
    n = _na(nombre)
    kw_re, ex_re = _patrones()
    if any(rx.search(n) for rx in ex_re):
        return False
    if any(rx.search(n) for rx in _cargar_aprendidas()):
        return False
    return any(rx.search(n) for rx in kw_re)


def listar_dia(fecha_ddmmaaaa: str) -> list[dict]:
    data = _get({"fecha": fecha_ddmmaaaa, "ticket": TICKET})
    return data.get("Listado", [])


def traer_detalle(codigo: str) -> dict:
    data = _get({"codigo": codigo, "ticket": TICKET})
    lst = data.get("Listado", [])
    return lst[0] if lst else {}


def _aplanar_detalle(d: dict) -> dict:
    comprador = d.get("Comprador") or {}
    fechas = d.get("Fechas") or {}
    region = (comprador.get("RegionUnidad") or "").strip() or None
    return {
        "codigo": d.get("CodigoExterno"),
        "nombre": d.get("Nombre"),
        "organismo": comprador.get("NombreOrganismo") or comprador.get("NombreUnidad"),
        "region": region,
        "comuna": (comprador.get("ComunaUnidad") or "").strip() or None,
        "modalidad": d.get("Modalidad"),
        "monto_estimado": d.get("MontoEstimado"),
        "moneda": d.get("Moneda"),
        "fecha_cierre": fechas.get("FechaCierre") or d.get("FechaCierre"),
        "fecha_visita": fechas.get("FechaVisitaTerreno"),
        "tipo_pago": d.get("TipoPago"),
        "estado_mp": d.get("CodigoEstado"),
        "descripcion": (d.get("Descripcion") or "")[:2000],
        "prohibicion_subc": d.get("ProhibicionContratacion"),
        "subcontratacion": d.get("SubContratacion"),
        "direccion_visita": d.get("DireccionVisita"),
        "json_detalle": json.dumps(d, ensure_ascii=False),
    }


def correr_dia(fecha_ddmmaaaa: str, traer_detalles=True, pausa_detalle=1.0) -> dict:
    """Descubre el día, filtra por keywords, (opcional) trae detalle y persiste en SQLite."""
    db.init_db()
    listado = listar_dia(fecha_ddmmaaaa)
    candidatos = [x for x in listado if matchea(x.get("Nombre", ""))]
    nuevas = actualizadas = 0

    with db.conn() as c:
        for item in candidatos:
            codigo = item["CodigoExterno"]
            if traer_detalles:
                try:
                    det = traer_detalle(codigo)
                    row = _aplanar_detalle(det) if det else {
                        "codigo": codigo, "nombre": item.get("Nombre"),
                        "estado_mp": item.get("CodigoEstado"),
                    }
                    time.sleep(pausa_detalle)
                except Exception as e:
                    row = {"codigo": codigo, "nombre": item.get("Nombre"),
                           "estado_mp": item.get("CodigoEstado")}
                    db.log_evento(c, codigo, "error", f"detalle: {e}")
            else:
                row = {"codigo": codigo, "nombre": item.get("Nombre"),
                       "estado_mp": item.get("CodigoEstado")}
            res = db.upsert_licitacion(c, row)
            nuevas += res == "nueva"
            actualizadas += res == "actualizada"

    return {"fecha": fecha_ddmmaaaa, "total_dia": len(listado),
            "candidatos": len(candidatos), "nuevas": nuevas, "actualizadas": actualizadas}


if __name__ == "__main__":
    import sys
    fecha = sys.argv[1] if len(sys.argv) > 1 else time.strftime("%d%m%Y")
    # detalles=False para no chocar con el rate-limit del ticket de pruebas
    print(json.dumps(correr_dia(fecha, traer_detalles=False), indent=2, ensure_ascii=False))
