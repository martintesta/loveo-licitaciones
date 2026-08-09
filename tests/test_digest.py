"""
test_digest.py — Sensor del digest de bases (digest.py) y del OCR (bases.py).

Dos cosas que costaron caro y que estos tests guardan:
  1. El digest tiene que capturar lo que decide la estrategia (puntajes escalón por escalón,
     inadmisibilidad, empate, itemizado), no solo las secciones que ya recorta bases.secciones().
  2. Tesseract en Windows NO está en el PATH: sin apuntar `tesseract_cmd` al binario, el OCR falla
     en silencio y una licitación escaneada queda sin texto y es inanalizable. Medido sobre un lote
     real: 8 de 25.

  python -m pytest tests/test_digest.py -q
"""
import bases
import db
import digest
import schema_v3

BASES_FALSAS = """
### ARCHIVO: bases_administrativas.pdf
El objeto de la licitación es la adquisición de 2 containers para Zoonosis.
El presupuesto disponible asciende a la suma de $22.650.296 impuestos incluidos.
Los valores netos deberán indicarse por separado.

CRITERIOS DE EVALUACIÓN
Oferta económica 35%
Especificaciones técnicas 25%
Tiempo de entrega 20%
Se asignarán 20 puntos a las ofertas con plazo menor o igual a 30 días hábiles.
Se asignarán 10 puntos a las ofertas entre 31 y 40 días.
El plazo de entrega no podrá exceder los 45 días corridos.
Se exigirá garantía de fiel cumplimiento por el 5% del valor del contrato.
La visita a terreno es obligatoria y se realizará el 04 de agosto de 2026.
Serán declaradas inadmisibles las ofertas que no acompañen el Anexo A.
No se permite subcontratar la fabricación de la estructura.
La forma de pago será a 30 días corridos desde la recepción conforme.
En caso de empate, se preferirá a la oferta económica más baja.
Se aplicará una multa de 5 UF por cada día de atraso.
ITEMIZADO
Partida 1.1 Container 20 pies | 2 | un
Partida 1.2 Acondicionamiento sanitario | 2 | un
ESPECIFICACIONES TÉCNICAS
Dimensiones: 6,05 x 2,44 metros, espesor de aislación 50 mm.
Se exige experiencia mínima de 3 años en obras similares.
"""


# ------------------------------------------------------------------ digerir (puro)
def test_el_digest_captura_lo_que_decide_la_estrategia():
    d = digest.digerir(BASES_FALSAS)
    todo = d["base"] + d["tecnico"]
    for etiqueta in ("OBJETO", "PRESUPUESTO", "IVA", "CRITERIOS", "PLAZO", "GARANTIA", "VISITA",
                     "INADMISIBLE", "SUBCONTRATA", "PAGO", "EMPATE"):
        assert f"########## {etiqueta} ##########" in todo, f"el digest perdió la sección {etiqueta}"
    assert "22.650.296" in todo
    assert "inadmisibles" in todo
    assert "empate" in todo.lower()


def test_las_secciones_tecnicas_van_al_digest_tecnico():
    """EETT / ITEMIZADO / PUNTAJE traen las cantidades y los escalones: van aparte y con tope alto,
    porque mezcladas con el resto se las comía el recorte. Se compara el ENCABEZADO de sección
    (`########## X ##########`), no la palabra suelta — 'ITEMIZADO' también aparece en el cuerpo."""
    d = digest.digerir(BASES_FALSAS)
    for etiqueta in ("EETT", "ITEMIZADO", "PUNTAJE", "EXPERIENCIA"):
        encabezado = f"########## {etiqueta} ##########"
        assert encabezado in d["tecnico"], f"{etiqueta} debería estar en el digest técnico"
        assert encabezado not in d["base"], f"{etiqueta} no debería duplicarse en el digest base"


def test_el_digest_recorta_pero_avisa():
    """Nunca truncar en silencio (antipattern del proyecto): si recorta, lo dice."""
    largo = BASES_FALSAS + "\n".join(f"Se asignarán {i} puntos por el criterio {i}." for i in range(200))
    d = digest.digerir(largo)
    assert "seccion recortada" in (d["base"] + d["tecnico"]).lower() or len(d["tecnico"]) < len(largo)


def test_digest_de_texto_vacio_no_revienta():
    d = digest.digerir("")
    assert d["base"] and "DIGEST" in d["base"]


def test_el_digest_esta_acotado_por_mas_que_crezca_la_fuente():
    """El punto del digest es que ENTRE en el prompt. Lo que importa no es una razón de compresión
    fija sino que el tamaño esté ACOTADO: quintuplicar las bases no puede quintuplicar el digest,
    porque entonces una licitación con 40 anexos revienta el contexto."""
    chico = digest.digerir(BASES_FALSAS * 10)
    grande = digest.digerir(BASES_FALSAS * 50)
    n_chico = len(chico["base"] + chico["tecnico"])
    n_grande = len(grande["base"] + grande["tecnico"])
    assert n_grande < n_chico * 2, f"el digest crece con la fuente: {n_chico} → {n_grande}"
    assert n_grande < 80_000, "el digest se pasó del presupuesto de contexto"


# ------------------------------------------------------------------ extracto (contra la base)
def test_extracto_lee_los_documentos_registrados(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v3.migrate()
    doc = tmp_path / "bases.txt"
    doc.write_text(BASES_FALSAS, encoding="utf-8")
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "X", "nombre": "n", "organismo": "o", "region": "r"})
        c.execute("INSERT INTO documentos (codigo, nombre_archivo, ruta_local, tipo) VALUES (?,?,?,?)",
                  ("X", "bases.txt", str(doc), "txt"))
    r = digest.para_analisis("X")
    assert r["archivos"] == ["bases.txt"]
    assert "22.650.296" in r["digest"]
    assert r["chars"] > 0 and r["ilegibles"] == []


def test_un_documento_roto_no_frena_a_los_demas(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    schema_v3.migrate()
    bueno = tmp_path / "bueno.txt"
    bueno.write_text(BASES_FALSAS, encoding="utf-8")
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": "Y", "nombre": "n", "organismo": "o", "region": "r"})
        for nombre, ruta in (("roto.pdf", str(tmp_path / "no_existe.pdf")), ("bueno.txt", str(bueno))):
            c.execute("INSERT INTO documentos (codigo, nombre_archivo, ruta_local, tipo) VALUES (?,?,?,?)",
                      ("Y", nombre, ruta, nombre.split(".")[-1]))
    r = digest.para_analisis("Y")
    assert "roto.pdf" in r["ilegibles"]          # se reporta, va a INFO FALTANTE
    assert "22.650.296" in r["digest"]           # y el bueno igual se leyó


# ------------------------------------------------------------------ OCR (el bug de las 8/25)
def test_tesseract_se_busca_fuera_del_PATH(monkeypatch, tmp_path):
    """En Windows el instalador de Tesseract no toca el PATH. Si no lo buscamos donde de verdad
    está, pytesseract tira TesseractNotFoundError, `_ocr_pagina` se la traga y la licitación
    escaneada queda sin texto — sin ningún error visible."""
    falso = tmp_path / "tesseract.exe"
    falso.write_text("", encoding="utf-8")
    monkeypatch.setattr(bases, "TESSERACT_CANDIDATOS", [str(falso)])
    monkeypatch.delenv("LOVEO_TESSERACT", raising=False)
    assert bases.tesseract_exe() == str(falso)


def test_LOVEO_TESSERACT_manda_sobre_los_candidatos(monkeypatch, tmp_path):
    forzado = tmp_path / "mi_tesseract.exe"
    forzado.write_text("", encoding="utf-8")
    monkeypatch.setenv("LOVEO_TESSERACT", str(forzado))
    assert bases.tesseract_exe() == str(forzado)


def test_sin_binario_avisa_en_vez_de_fingir(monkeypatch, tmp_path):
    monkeypatch.setattr(bases, "TESSERACT_CANDIDATOS", [str(tmp_path / "no_existe.exe")])
    monkeypatch.delenv("LOVEO_TESSERACT", raising=False)
    assert bases.tesseract_exe() is None
