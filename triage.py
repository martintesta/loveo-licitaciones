"""
triage.py — Embudo de filtros duros. Reemplaza al score provisional como puerta de entrada.

POR QUÉ SE CAMBIÓ LA ARQUITECTURA
El score anterior era una suma ponderada de 6 dimensiones. Dos de ellas (margen, complejidad) no
se podían calcular sin las bases y quedaban fijas en 5/10, lo que ponía 25 puntos constantes en
todo ítem y dejaba el rango real en 43-84 sobre una escala nominal de 120. El umbral de
"Priorizar" estaba en 85: **inalcanzable por construcción**, y nunca disparó en 186 licitaciones.

Pero el problema de fondo no era el umbral. De 33 licitaciones cerradas en una semana, 32 se
decidieron por tres motivos —no es nuestro producto, no alcanza el presupuesto, se pasó la visita—
que son **binarios y eliminatorios**. Una suma ponderada permite que un buen puntaje logístico
compense estar en cualquiera de los tres, y eso es exactamente lo que pasó: "Desarrollo de la
plataforma modular de compras" (software) sacó 84, el máximo del sistema.

Un AND lógico no se modela con un promedio. Acá los filtros son filtros.

  gate_producto(lic)    -> ¿es lo que Loveo fabrica?
  gate_calendario(lic)  -> ¿llegamos a tiempo?
  gate_presupuesto(lic) -> ¿alcanza la plata?  (PENDIENTE: necesita la tabla de costo paramétrico)
  evaluar(lic)          -> corre los gates en serie y devuelve dónde murió

  python triage.py <CODIGO>      # explica gate por gate
  python triage.py --auditar     # corre el embudo sobre toda la base y contrasta con lo decidido
"""
import json
import os
import re
from datetime import datetime

from textnorm import na as _na, pat as _pat

# ---------------------------------------------------------------------------
# GATE 1 — ¿Es el producto de Loveo?
# ---------------------------------------------------------------------------
# Las familias salen de la EVIDENCIA, no de una lista escrita a mano: se cruzó la categoría
# ONU/UNSPSC (que la API entrega en el 100% de los casos y nadie estaba usando) contra las 33
# decisiones reales ya registradas. Donde la evidencia es ambigua o el n es 1, la familia NO va
# a ninguna lista: cae a las palabras clave. Con 33 decisiones, una blocklist de familias con
# n=1 sería sobreajuste, no aprendizaje.

# n=47, 1 solo descarte por fuera-de-core · n=41, 1 solo descarte por fuera-de-core.
FAMILIAS_CORE = {
    "3020": "Estructuras prefabricadas, obras y construcciones",
    "7213": "Servicios de construcción y mantenimiento",
    "3022": "Construcciones prefabricadas",
    "3016": "Materiales de construcción",
    "3010": "Materiales estructurales",
    "3019": "Equipamiento para obras",
}
# Familias donde TODO lo decidido fue "fuera de core", y que además son semánticamente
# inconfundibles: no hay lectura razonable en que Loveo fabrique esto.
FAMILIAS_FUERA = {
    "7612": "Eliminación y tratamiento de residuos (el servicio, no la sala REAS)",
    "7611": "Servicios de limpieza",
    "7613": "Limpieza de residuos",
    "4710": "Tratamiento y suministro de agua", "4712": "Equipo de limpieza",
    "4713": "Suministros de limpieza",
    "8010": "Consultorías de gestión", "8011": "Servicios profesionales y consultorías",
    "8013": "Servicios profesionales", "8016": "Servicios profesionales",
    "4320": "Tecnologías de la información", "4321": "TI", "4322": "TI", "4323": "Telecomunicaciones",
    "5610": "Muebles de alojamiento", "5611": "Muebles comerciales e industriales",
    "5612": "Mobiliario institucional", "5212": "Electrodomésticos", "5214": "Electrodomésticos",
    "6010": "Juegos, juguetes y material didáctico", "6014": "Juegos y juguetes",
    "4223": "Nutrición clínica (fórmulas y alimentos)", "4224": "Productos medicinales",
    "2413": "Refrigeración y contenedores refrigerados",
    "2510": "Vehículos motorizados", "2511": "Embarcaciones",
    "9010": "Viajes, alimentación y alojamiento", "9015": "Viajes y alimentación",
    "9111": "Servicio doméstico y cuidado personal",
    "8611": "Educación y capacitación",
    "7812": "Transporte, almacenaje y correo",
    "8310": "Servicios básicos e información pública",
    "4412": "Suministros de oficina",
}

# Un token de "modular" solo cuenta si viene con un objeto FÍSICO al lado. Sin esta regla,
# "plataforma modular de compras" (software) matcheaba igual que un contenedor.
TOKENS_MODULAR = ["modular", "modulares", "modulo", "módulo", "modulos", "módulos"]
TOKENS_OBJETO = ["contenedor", "contenedores", "container", "containers", "conteiner",
                 "sala", "salas", "oficina", "oficinas", "bano", "baño", "banos", "baños",
                 "camarin", "camarín", "camarines", "box", "pabellon", "pabellón",
                 "bodega", "clinica", "clínica", "vestidor", "vestidores", "habitable",
                 "sede", "sedes", "aula", "aulas", "policlinico", "policlínico",
                 # agregados tras la auditoría: los seis falsos positivos del primer corte
                 "unidad", "unidades", "administrativo", "administrativos", "hospital",
                 "cesfam", "cecosf", "posta", "escuela", "laboratorio", "lavanderia",
                 "lavandería", "camarines", "recinto", "dependencia", "dependencias"]
# Producto core que se reconoce solo, sin necesitar la regla de coexistencia.
TOKENS_CORE = ["contenedor", "contenedores", "container", "containers", "conteiner",
               "box dental", "box veterinario", "sala reas", "reas", "respel", "suspel",
               "bano modular", "baño modular", "sala modular", "oficina modular",
               "mediagua", "mediaguas",
               # Loveo persigue fotovoltaico de hecho: 4 licitaciones vivas en revisión. Se
               # reconoce como core hasta que el negocio diga lo contrario — la asimetría manda.
               "fotovoltaico", "fotovoltaica", "fotovoltaicos", "fotovoltaicas"]
# Negativas DURAS: nombran un producto que Loveo no fabrica. Matan siempre, haya o no core.
TOKENS_NEGATIVOS_DUROS = [
    "software", "plataforma", "sistema informatico", "sistema informático", "aplicacion movil",
    "juego infantil", "juegos infantiles", "juegos modulares", "juego modular",
    "en polvo", "nutricional", "formula lactea", "fórmula láctea", "alimenticio",
    "polibrazo", "ampliroll", "carroceria", "carrocería", "tolva",
    "capacitacion", "capacitación", "consultoria", "consultoría", "mobiliario",
]
# Negativas MODIFICADORAS: sólo matan si están pegadas al sustantivo core, porque ahí lo
# califican en vez de acompañarlo. La diferencia es real y decide dos casos opuestos:
#   "contenedores REFRIGERADOS"                         -> el producto es un reefer   -> descarta
#   "contenedor de oficina con equipo de refrigeración" -> el producto es la oficina  -> pasa
# Sin esta distinción hay que elegir entre dejar entrar los reefers o descartar cualquier
# contenedor que mencione un aire acondicionado.
TOKENS_NEGATIVOS_MODIF = [
    "refrigerado", "refrigerados", "refrigerada", "refrigeradas", "refrigeracion", "refrigeración",
    "frigorifico", "frigorífico", "reefer", "camara de frio", "cámara de frío",
    "open top", "camion", "camión", "de frio", "de frío",
]
PALABRAS_DE_DISTANCIA = int(os.environ.get("LOVEO_TRIAGE_DISTANCIA", "1"))

_RX_NEG_DURO = [(_pat(t), t) for t in TOKENS_NEGATIVOS_DUROS]
_RX_NEG_MODIF = [(_pat(t), t) for t in TOKENS_NEGATIVOS_MODIF]
_RX_CORE = [(_pat(t), t) for t in TOKENS_CORE]
_RX_MODULAR = [(_pat(t), t) for t in TOKENS_MODULAR]
_RX_OBJETO = [(_pat(t), t) for t in TOKENS_OBJETO]


def _palabras_entre(texto, a, b):
    """Cuántas palabras hay entre dos tramos del texto. 0 = pegados."""
    ini, fin = (a[1], b[0]) if a[1] <= b[0] else (b[1], a[0])
    return len([w for w in texto[ini:fin].split() if w])


def _negativas(texto):
    """(duras, modificadoras_pegadas_al_core, modificadoras_sueltas).

    Una negativa modificadora cuenta como dura sólo si toca al sustantivo core."""
    duras = [tok for rx, tok in _RX_NEG_DURO if rx.search(texto)]
    cores = [(m.span(), tok) for rx, tok in _RX_CORE for m in [rx.search(texto)] if m]
    pegadas, sueltas = [], []
    for rx, tok in _RX_NEG_MODIF:
        m = rx.search(texto)
        if not m:
            continue
        if any(_palabras_entre(texto, m.span(), sp) <= PALABRAS_DE_DISTANCIA for sp, _ in cores):
            pegadas.append(tok)
        else:
            sueltas.append(tok)
    return duras, pegadas, sueltas


def familia_onu(lic):
    """('3020', 'Artículos para estructuras…') del primer ítem, o (None, None).
    El código ONU está en el 100% de los detalles y no lo usaba nadie."""
    crudo = lic.get("json_detalle") or lic.get("_detalle")
    try:
        d = json.loads(crudo) if isinstance(crudo, str) else (crudo or {})
        items = (d.get("Items") or {}).get("Listado") or []
        if not items:
            return None, None
        cod = str(items[0].get("CodigoCategoria") or "")
        return (cod[:4] if len(cod) >= 4 else None), str(items[0].get("Categoria") or "")[:80]
    except (ValueError, TypeError, AttributeError):
        return None, None


def _texto(lic, sin_lugar=False):
    """Título Y descripción. El modelo viejo miraba sólo el título — ahí se colaban los falsos
    positivos, porque el título es donde el comprador pone la palabra de moda.

    `sin_lugar=True` borra antes el nombre de la comuna y la región. Hace falta: la exclusión
    curada 'puente' (pensada para obras de puente) matcheaba en «Puente Alto» y mataba una
    licitación del Hospital Sótero del Río. El topónimo entró recién al leer la descripción, que
    es justamente la mejora — y trajo el problema con ella."""
    t = f"{lic.get('nombre') or ''} . {lic.get('descripcion') or ''}"
    if sin_lugar:
        for lugar in (lic.get("comuna"), lic.get("region")):
            for palabra in re.split(r"[\s,]+", str(lugar or "")):
                if len(palabra) > 3:
                    t = re.sub(rf"\b{re.escape(palabra)}\b", " ", t, flags=re.I)
    return _na(t)


_CACHE_EXCLUIR = None


def _excluir_curadas():
    """Las exclusiones que Martín ya curó en la tabla `keywords` (31 activas hoy).

    Se consultan en vez de mantener una segunda lista acá: son la misma decisión de negocio y
    dos listas paralelas divergen. Si la BD no está disponible (tests unitarios), se degrada a
    vacío en vez de fallar."""
    global _CACHE_EXCLUIR
    if _CACHE_EXCLUIR is None:
        try:
            import keywords
            _, exc, _ = keywords.get_active_lists()
            _CACHE_EXCLUIR = [(_pat(t), t) for t in exc]
        except Exception:
            _CACHE_EXCLUIR = []
    return _CACHE_EXCLUIR


def gate_producto(lic, excluir=None):
    """¿Es lo que Loveo fabrica? Devuelve {pasa, motivo, senal, confianza}.

    Orden de decisión: exclusiones curadas → negativas duras → negativa que califica al core →
    familia ONU fuera (sólo si no hay señal positiva) → core → familia ONU core → coexistencia.
    `confianza='baja'` significa que hay que mirarlo a mano (o mandarlo a un clasificador).

    `excluir` es inyectable para tests: lista de términos, o [] para no consultar la tabla."""
    t = _texto(lic)
    fam, fam_nombre = familia_onu(lic)

    curadas = ([(_pat(x), x) for x in excluir] if excluir is not None else _excluir_curadas())
    t_sin_lugar = _texto(lic, sin_lugar=True)
    hit = next((tok for rx, tok in curadas if rx.search(t_sin_lugar)), None)
    if hit:
        return {"pasa": False, "motivo": f"exclusión curada del negocio: '{hit}'",
                "senal": "keyword_excluida", "confianza": "alta", "familia": fam}

    duras, pegadas, sueltas = _negativas(t)
    core = [tok for rx, tok in _RX_CORE if rx.search(t)]

    if duras:
        return {"pasa": False, "motivo": f"palabra excluyente: {', '.join(duras[:3])}",
                "senal": "negativa", "confianza": "alta", "familia": fam}
    if pegadas:
        return {"pasa": False,
                "motivo": f"'{pegadas[0]}' califica al producto, no lo acompaña "
                          f"({'contenedor refrigerado' if core else 'sin core'})",
                "senal": "negativa_modificadora", "confianza": "alta", "familia": fam}
    if sueltas and not core:
        return {"pasa": False, "motivo": f"palabra excluyente: {', '.join(sueltas[:3])}",
                "senal": "negativa", "confianza": "alta", "familia": fam}
    modular = [tok for rx, tok in _RX_MODULAR if rx.search(t)]
    objeto = [tok for rx, tok in _RX_OBJETO if rx.search(t)]
    positivo = bool(core or (modular and objeto))

    # La familia ONU NO mata por sí sola cuando el texto sí muestra producto. La auditoría contra
    # las decisiones reales mostró por qué: la lavandería modular del Ejército está clasificada
    # como "9111 servicio doméstico" y los modulares de Recoleta como "5611 muebles". El código ONU
    # dice cómo archivó la compra el comprador, no qué se fabrica. Sirve para desempatar, no para
    # sentenciar.
    if fam in FAMILIAS_FUERA and not positivo:
        return {"pasa": False, "motivo": f"familia ONU {fam} — {FAMILIAS_FUERA[fam]}",
                "senal": "onu_fuera", "confianza": "alta", "familia": fam}
    if sueltas and core:
        return {"pasa": True, "motivo": f"core '{core[0]}' con '{sueltas[0]}' mencionado aparte "
                                        f"— revisar a mano",
                "senal": "conflicto", "confianza": "baja", "familia": fam}
    if core:
        conf = "baja" if fam in FAMILIAS_FUERA else "alta"
        return {"pasa": True, "motivo": f"producto core: {core[0]}"
                                        + (f" (pero archivada en ONU {fam})" if conf == "baja" else ""),
                "senal": "core", "confianza": conf, "familia": fam}
    if fam in FAMILIAS_CORE:
        return {"pasa": True, "motivo": f"familia ONU {fam} — {FAMILIAS_CORE[fam]}",
                "senal": "onu_core", "confianza": "media", "familia": fam}
    if modular and objeto:
        return {"pasa": True, "motivo": f"'{modular[0]}' junto a objeto físico '{objeto[0]}'",
                "senal": "coexistencia", "confianza": "media", "familia": fam}
    # 'modular' suelto NO mata: pasa a revisión. Un falso positivo del embudo cuesta una
    # licitación; un falso negativo cuesta horas. Con esa asimetría, la duda deja pasar.
    # Los casos de software mueren igual, pero por su negativa dura ('plataforma', 'software'),
    # que es una razón explícita y no una inferencia por ausencia.
    if modular:
        return {"pasa": True, "motivo": f"'{modular[0]}' sin objeto físico claro — revisar",
                "senal": "modular_suelto", "confianza": "baja", "familia": fam}
    return {"pasa": False, "motivo": "sin señal de producto Loveo"
                                     f"{f' (familia ONU {fam}: {fam_nombre})' if fam else ''}",
            "senal": "sin_senal", "confianza": "baja", "familia": fam}


# ---------------------------------------------------------------------------
# GATE 3 — ¿Llegamos a tiempo?
# ---------------------------------------------------------------------------
# ADVERTENCIA sobre el diseño original: se especificó este gate sobre `Fechas.FechaVisitaTerreno`
# del API. Ese campo viene **null en el 100% de los casos medidos** (40/40 con detalle), así que
# un gate montado sólo sobre él no dispararía nunca — sería un segundo umbral inalcanzable, el
# mismo bug que este rediseño vino a corregir.
# La fecha de visita real se lee del PLIEGO (`visitas.py`), y eso ocurre DESPUÉS de descargar las
# bases. Por lo tanto este gate es RE-EVALUABLE: al descubrir casi nunca puede decidir, y al
# ingestar las bases sí. Se devuelve `evaluable=False` cuando no hay dato, en vez de dejar pasar
# en silencio como si no hubiera visita.
REGIONES_BASE = ("los lagos", "metropolitana")


def _fecha(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace(" ", "T")[:19])
    except ValueError:
        return None


def gate_calendario(lic, hoy=None):
    """¿La visita obligatoria ya pasó? Devuelve {pasa, evaluable, motivo, banderas}."""
    hoy = hoy or datetime.now()
    banderas = []

    # Bandera informativa: criterios de "desarrollo local" que dan 0 a un oferente de otra región.
    region = _na(lic.get("region") or "")
    organismo = _na(lic.get("organismo") or "")
    if "municipalidad" in organismo and region and not any(b in region for b in REGIONES_BASE):
        banderas.append("riesgo_desarrollo_local")

    caracter = (lic.get("visita_caracter") or "").strip()
    fecha_api = _fecha(lic.get("fecha_visita"))
    fecha_txt = lic.get("visita_fecha_txt") or ""

    if caracter in ("prohibida", "sin_visita"):
        return {"pasa": True, "evaluable": True, "motivo": "el pliego no contempla visita",
                "banderas": banderas}
    if fecha_api:
        if fecha_api.date() < hoy.date():
            return {"pasa": False, "evaluable": True,
                    "motivo": f"visita a terreno del {fecha_api:%d-%m-%Y} ya pasó",
                    "banderas": banderas}
        return {"pasa": True, "evaluable": True,
                "motivo": f"visita el {fecha_api:%d-%m-%Y}, aún alcanzamos", "banderas": banderas}
    if caracter in ("obligatoria", "puntuada"):
        f = _fecha_literal(fecha_txt, hoy)
        if f and f.date() < hoy.date():
            return {"pasa": False, "evaluable": True,
                    "motivo": f"visita {caracter} del pliego ({fecha_txt}) ya pasó",
                    "banderas": banderas}
        return {"pasa": True, "evaluable": bool(f),
                "motivo": f"visita {caracter} detectada en el pliego"
                          + (f", fecha {fecha_txt}" if fecha_txt else " SIN FECHA LEGIBLE"),
                "banderas": banderas + ["visita_" + caracter]}
    return {"pasa": True, "evaluable": False,
            "motivo": "sin dato de visita (el API la trae null y aún no se leyó el pliego)",
            "banderas": banderas}


_RX_DMA = re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})")
_MESES = {m: i for i, m in enumerate(
    ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
     "septiembre", "octubre", "noviembre", "diciembre"], 1)}
_RX_LITERAL = re.compile(r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+(?:de\s+)?(\d{4})", re.I)


def _fecha_literal(txt, hoy):
    """La fecha que `visitas.py` sacó del pliego es orientativa y viene como texto libre."""
    if not txt:
        return None
    m = _RX_DMA.search(txt)
    if m:
        d, mes, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
        a = a + 2000 if a < 100 else a
        try:
            return datetime(a, mes, d)
        except ValueError:
            return None
    m = _RX_LITERAL.search(_na(txt))
    if m and m.group(2) in _MESES:
        try:
            return datetime(int(m.group(3)), _MESES[m.group(2)], int(m.group(1)))
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# GATE 2 — ¿Alcanza el presupuesto?  (PENDIENTE)
# ---------------------------------------------------------------------------
# No se implementa todavía a propósito. Necesita una tabla de costo paramétrico (CLP/m² y
# CLP/módulo) con 6-10 precios unitarios REALES del negocio. Inventar esos números daría un gate
# que descarta licitaciones con una cifra imaginaria, que es peor que no tener gate.
#
# Nota sobre los divisores: los actuales (1,625 y 1,885) son markup SOBRE COSTO
# (1,30 × 1,25 y 1,30 × 1,45). Si la política de 25%/35-40% es margen SOBRE PRECIO DE VENTA
# —lo habitual en construcción— los correctos son 1,733 (1,30/0,75) y 2,000-2,167 (1,30/0,65 y
# 1,30/0,60). La diferencia autoriza precios 6-13% más bajos de lo que la política permite.
# NO se cambió: es una decisión de negocio, no un bug de código. Queda como parámetro.
MARGEN_SOBRE = os.environ.get("LOVEO_MARGEN_SOBRE", "costo")     # "costo" | "venta"
SOBRECOSTO = float(os.environ.get("LOVEO_SOBRECOSTO", "0.30"))
MARGEN_MIN = float(os.environ.get("LOVEO_MARGEN_MIN", "0.25"))
MARGEN_OBJ = float(os.environ.get("LOVEO_MARGEN_OBJ", "0.35"))


def divisores():
    """(límite, sano): costo base máximo = techo_neto / divisor. Depende de la convención."""
    f = 1 + SOBRECOSTO
    if MARGEN_SOBRE == "venta":
        return f / (1 - MARGEN_MIN), f / (1 - MARGEN_OBJ)
    return f * (1 + MARGEN_MIN), f * (1 + MARGEN_OBJ)


def gate_presupuesto(lic):
    """Placeholder explícito: deja pasar y marca que falta el dato, en vez de fingir que evaluó."""
    return {"pasa": True, "evaluable": False,
            "motivo": "Gate 2 pendiente: falta la tabla de costo paramétrico del negocio",
            "monto": lic.get("monto_estimado")}


# ---------------------------------------------------------------------------
# El embudo
# ---------------------------------------------------------------------------
GATES = (("producto", gate_producto), ("presupuesto", gate_presupuesto), ("calendario", None))


def evaluar(lic, hoy=None):
    """Corre los gates en serie. El primero que falla decide y corta.

    Devuelve {pasa, gate_fallado, motivo, banderas, gates:{...}}. No hay score: si sobrevive los
    filtros, el orden lo pone el ranker (etapa 3), no un número de opinión."""
    res, banderas = {}, []
    g1 = gate_producto(lic)
    res["producto"] = g1
    if not g1["pasa"]:
        return {"pasa": False, "gate_fallado": "producto", "motivo": g1["motivo"],
                "banderas": [], "gates": res}

    g2 = gate_presupuesto(lic)
    res["presupuesto"] = g2
    if not g2["pasa"]:
        return {"pasa": False, "gate_fallado": "presupuesto", "motivo": g2["motivo"],
                "banderas": [], "gates": res}

    g3 = gate_calendario(lic, hoy)
    res["calendario"] = g3
    banderas += g3.get("banderas") or []
    if not g3["pasa"]:
        return {"pasa": False, "gate_fallado": "calendario", "motivo": g3["motivo"],
                "banderas": banderas, "gates": res}

    pendientes = [k for k, v in res.items() if v.get("evaluable") is False]
    return {"pasa": True, "gate_fallado": None,
            "motivo": g1["motivo"], "banderas": banderas,
            "confianza": g1["confianza"], "gates_pendientes": pendientes, "gates": res}


def registrar(codigo, res=None, lic=None):
    """Persiste el resultado del embudo en `licitaciones.triage_*`. Devuelve el resultado.

    Guarda en qué gate murió y por qué regla, no un puntaje: lo que hace falta acumular para
    poder auditar el filtro es el MOTIVO, no un número. Nunca propaga excepciones."""
    import db
    import schema_v3
    try:
        schema_v3.migrate()
        if res is None:
            if lic is None:
                with db.conn() as c:
                    fila = c.execute("SELECT * FROM licitaciones WHERE codigo=?", (codigo,)).fetchone()
                lic = dict(fila) if fila else None
            if not lic:
                return None
            res = evaluar(lic)
        g = (res.get("gates") or {}).get(res.get("gate_fallado") or "producto") or {}
        with db.conn() as c:
            c.execute("UPDATE licitaciones SET triage_gate=?, triage_senal=?, triage_motivo=?, "
                      "triage_confianza=?, triage_at=? WHERE codigo=?",
                      (res.get("gate_fallado"), g.get("senal"), (res.get("motivo") or "")[:300],
                       res.get("confianza") or g.get("confianza"), db._now(), codigo))
        return res
    except Exception:
        return res


def etiquetar(codigo, es_producto, nota=""):
    """Etiqueta humana `es_producto_loveo` (1/0): el set de entrenamiento y de evaluación."""
    import db
    import schema_v3
    schema_v3.migrate()
    with db.conn() as c:
        c.execute("UPDATE licitaciones SET es_producto_loveo=? WHERE codigo=?",
                  (1 if es_producto else 0, codigo))
        db.log_evento(c, codigo, "triage",
                      f"etiqueta humana: {'ES' if es_producto else 'NO ES'} producto Loveo. {nota}")


if __name__ == "__main__":
    import sys
    import db
    args = sys.argv[1:]
    if args and args[0] == "--auditar":
        import auditoria_triage
        auditoria_triage.correr()
    elif args:
        with db.conn() as c:
            r = c.execute("SELECT * FROM licitaciones WHERE codigo=?", (args[0],)).fetchone()
        print(json.dumps(evaluar(dict(r)), indent=2, ensure_ascii=False, default=str))
    else:
        print(__doc__)
