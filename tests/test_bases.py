"""
test_bases.py — Sensor del recorte por secciones (lógica pura sobre texto, sin PDF).

bases.secciones() parte el texto por los encabezados típicos de las bases de MP. Es lo que
decide qué fragmentos se le mandan a la Capa C, así que conviene cubrirlo.

  python -m pytest tests/test_bases.py -q
"""
import bases


def test_secciones_detecta_encabezados_tipicos():
    texto = (
        "Antecedentes generales del llamado.\n"
        "El presupuesto disponible es de $50.000.000.\n"
        "El plazo de entrega es de 60 dias corridos.\n"
        "Se exige garantia de fiel cumplimiento del contrato.\n"
        "Criterios de evaluacion: precio 60%, experiencia 40%.\n"
    )
    secs = bases.secciones(texto)
    assert "presupuesto" in secs
    assert "plazo" in secs
    assert "garantias" in secs
    assert "evaluacion" in secs


def test_secciones_sin_encabezados_vacio():
    assert bases.secciones("texto sin nada que reconocer por aqui") == {}


def test_normalizar_con_mapa_apunta_al_original():
    """El mapa debe devolver, para cada char del normalizado, el índice ORIGINAL que lo produjo
    (bug de auditoría: se buscaba en normalizado y se recortaba el original → secciones corridas)."""
    t = 'Introducción • objeto — "proyecto" a 20°C … ñandú'
    n, mapa = bases._normalizar_con_mapa(t)
    assert n[:12] == "introduccion"                  # sin acentos y en minúsculas
    assert "ñ" not in n and "nandu" in n
    assert len(mapa) == len(n) + 1                   # +1 por el centinela de fin
    for i, ch in enumerate(n):                       # cada char apunta a su origen real
        assert mapa[i] < len(t)
    p = n.find("nandu")
    assert t[mapa[p]] == "ñ"                         # traduce de vuelta al char original


def test_secciones_con_ligadura_no_rompe_la_palabra():
    """Los PDFs traen ligaduras ('ﬁ'): al expandir NFKD ocupan 2 chars. Si se truncaban, quedaba
    'fnanciamiento' y la sección NO se detectaba."""
    t = "Antecedentes\nEl ﬁnanciamiento es municipal y cubre la obra completa."
    secs = bases.secciones(t)
    assert "presupuesto" in secs                     # antes: {} (no detectaba nada)
    assert "nanciamiento" in secs["presupuesto"]


def test_secciones_con_simbolos_recorta_en_el_lugar_correcto():
    """Regresión: con viñetas/dashes/comillas antes del encabezado, la sección arrancaba corrida
    (se buscaba sobre texto normalizado que BORRABA esos símbolos y se recortaba el original)."""
    texto = ('INTRODUCCIÓN • objeto — alcance del "proyecto" a 20°C … y más\n'
             'PRESUPUESTO disponible: 50.000.000 pesos\n'
             'PLAZO DE ENTREGA: 60 dias\n')
    secs = bases.secciones(texto)
    assert secs["presupuesto"].startswith("PRESUPUESTO disponible")   # antes: texto de la intro
    assert "50.000.000" in secs["presupuesto"]
    assert secs["plazo"].startswith("PLAZO DE ENTREGA")


# ---------------------------------------------------------------------------
# Selección del encabezado REAL (no el del índice) — antes se tomaba la primera
# coincidencia y en los pliegos con índice se capturaba la línea del índice.
# ---------------------------------------------------------------------------

def test_secciones_prefiere_la_matriz_real_y_no_el_indice():
    texto = (
        "INDICE\n"
        "5. Criterios de evaluacion .......... pagina 12\n"
        "6. Garantias ........................ pagina 15\n"
        "\n" + ("relleno administrativo sin cifras.\n" * 40) +
        "5. CRITERIOS DE EVALUACION\n"
        "Precio 60% - Plazo 25% - Experiencia 15%\n"
        "Se asignaran 100 puntos a la oferta mas economica.\n"
    )
    ev = bases.secciones(texto)["evaluacion"]
    assert "60%" in ev, "debe capturar la matriz real, no la linea del indice"
    assert "pagina 12" not in ev


def test_densidad_senal_distingue_indice_de_matriz():
    # el relleno debe superar VENTANA_SENAL para que la mencion del indice no "vea" la matriz
    relleno = "x" * (bases.VENTANA_SENAL + 200)
    n, _ = bases._normalizar_con_mapa(
        "criterios de evaluacion, ver mas adelante\n" + relleno +
        "\ncriterios de evaluacion\nprecio 60% plazo 25% puntaje maximo 100")
    assert bases._densidad_senal(n, n.rindex("criterios")) > bases._densidad_senal(n, 0)


def test_secciones_ignora_entradas_de_indice_con_puntos_guia():
    n, _ = bases._normalizar_con_mapa("5. criterios de evaluacion ........... 12")
    assert bases._es_linea_de_indice(n, n.index("criterios"))
    n2, _ = bases._normalizar_con_mapa("5. CRITERIOS DE EVALUACION\nprecio 60%")
    assert not bases._es_linea_de_indice(n2, n2.index("criterios"))


# ---------------------------------------------------------------------------
# Limpieza previa al envío a Claude: dedup entre documentos y boilerplate legal.
# ---------------------------------------------------------------------------

def test_dedup_lineas_saca_repetidos_entre_documentos():
    linea = "El plazo de ejecucion de la obra sera de noventa dias corridos."
    a, b = bases.dedup_lineas([f"unico A\n{linea}", f"unico B\n{linea}"])
    assert linea in a and linea not in b
    assert "unico B" in b


def test_dedup_lineas_no_toca_lineas_cortas():
    a, b = bases.dedup_lineas(["Total", "Total"])
    assert a == "Total" and b == "Total"


def test_sin_boilerplate_saca_relleno_legal_y_conserva_lo_util():
    texto = ("Pagina 3 de 28\n"
             "Este documento ha sido firmado electronicamente de acuerdo con la ley N 19.799.\n"
             "El presupuesto disponible es de $50.000.000.\n")
    out = bases.sin_boilerplate(texto)
    assert "presupuesto disponible" in out
    assert "firmado electronicamente" not in out
    assert "Pagina 3 de 28" not in out


# ---------------------------------------------------------------------------
# Calidad de texto: detectar OCR fallido (manuscrito) sin marcar itemizados,
# que legítimamente traen muchas cifras y separadores de tabla.
# ---------------------------------------------------------------------------

def test_calidad_texto_marca_salida_de_ocr_sobre_manuscrito():
    basura = " ".join(["HoRADENCIO", "GonzZa", "lez", "I$pn]", "Ol", "uates", "W+bku", "7~Ma"] * 20)
    assert bases.calidad_texto(basura) < bases.CALIDAD_MINIMA


def test_calidad_texto_no_marca_un_itemizado_lleno_de_cifras():
    itemizado = "\n".join(
        f"{i}.1 | terciado estructural de dieciocho milimetros | m2 | {i*3} | 19000 | {i*57000}"
        for i in range(1, 40))
    assert bases.calidad_texto(itemizado) >= bases.CALIDAD_MINIMA


def test_calidad_texto_ignora_documentos_demasiado_cortos():
    assert bases.calidad_texto("dos palabras") == 1.0


def test_es_critico_reconoce_actas_de_visita():
    assert bases.es_critico("ACTA_VISITA_TERRENO_MODULOS.pdf")
    assert not bases.es_critico("Bases_Administrativas.pdf")


# ---------------------------------------------------------------------------
# Visita a terreno leida del pliego. El API de Mercado Publico devuelve
# Fechas.FechaVisitaTerreno en null casi siempre, asi que alertas.py nunca se
# disparaba; cuando la visita es excluyente define quien puede ofertar.
# ---------------------------------------------------------------------------

def test_visita_detecta_obligatoria_excluyente():
    v = bases.visita_a_terreno(
        "c) Fecha de visita a terreno obligatoria: 3 dias corridos posteriores a la fecha de "
        "publicacion de las Bases, a las 16:00 horas, en la garita de la Universidad.")
    assert v["menciona"] and v["obligatoria"]
    assert not v["prohibida"]


def test_visita_detecta_la_que_solo_da_puntaje():
    v = bases.visita_a_terreno(
        "Visita a Terreno: A las 10:00 del dia 03 de agosto de 2026, en Justicia Social 185.\n"
        "El oferente asiste a la visita a terreno 100 puntos\n"
        "El oferente NO asiste a la visita a terreno 0 puntos")
    assert v["puntuada"] and not v["obligatoria"]
    assert "03 de agosto de 2026" in (v["fecha_literal"] or "")


def test_visita_detecta_cuando_esta_prohibida():
    v = bases.visita_a_terreno(
        "Dado que la visita a terreno se encuentra prohibida, conforme a lo establecido en el "
        "articulo respectivo, las consultas se haran por el foro.")
    assert v["menciona"] and v["prohibida"]


def test_visita_reconoce_la_variante_visita_de_terreno():
    # las tablas y el OCR entregan 'Visita de Terreno' e incluso pegado, sin espacios
    assert bases.visita_a_terreno("VisitadeTerreno Martes 4 de agosto del 2026")["menciona"]
    assert bases.visita_a_terreno("Visita de Terreno: 4 de agosto")["menciona"]


def test_visita_no_inventa_cuando_el_pliego_no_la_menciona():
    v = bases.visita_a_terreno("Las consultas se formularan a traves del portal de Mercado Publico.")
    assert not v["menciona"] and not v["obligatoria"]
    assert v["fecha_literal"] is None


def test_visita_evalua_el_caracter_en_todas_las_menciones():
    # la fecha aparece en el cronograma y el puntaje en otro articulo, lejos
    texto = ("Visita a terreno: 03 de agosto de 2026 a las 10:00.\n" + ("relleno.\n" * 60) +
             "El oferente que no participe de esta visita tendra puntaje 0.")
    assert bases.visita_a_terreno(texto)["puntuada"]


def test_visita_no_confunde_el_final_de_terreno_con_la_negacion_no():
    """Regresion real: '\bno\b' sin limite de palabra matcheaba el final de 'terreNO Se
    realizara' y una visita OBLIGATORIA se leia como prohibida."""
    v = bases.visita_a_terreno(
        "10.- Visita a terreno Se realizara visita a terreno de caracter obligatoria, al tercer "
        "(3) dia corrido posterior a la fecha de publicacion de las bases, a las 10:00 horas.")
    assert v["obligatoria"] and not v["prohibida"]


def test_visita_ignora_la_clausula_condicional_de_inadmisibilidad():
    """Boilerplate frecuente: 'Cuando se disponga segun las Bases visita a terreno con caracter
    obligatorio...'. Es condicional: no significa que ESTA licitacion tenga visita."""
    texto = ("ARTICULO 10. VISITA A TERRENO. Las presentes bases no contemplan la realizacion de "
             "visitas tecnicas.\n"
             "-Cuando se disponga segun las Bases visita a terreno con caracter obligatorio, y "
             "algun oferente no concurriere a la hora y dia citado, sera inadmisible.")
    v = bases.visita_a_terreno(texto)
    assert not v["obligatoria"], "la clausula condicional no debe leerse como visita obligatoria"
    assert v["prohibida"]
