"""
test_montos.py — Sensor del extractor de presupuesto desde el pliego.

`MontoEstimado` del API viene null seguido y la cifra está en el documento con otro nombre. Lo
peligroso no es no encontrarla: es encontrar la equivocada. Los dos falsos positivos reales que
aparecieron el primer día están cubiertos abajo con su caso literal.

  python -m pytest tests/test_montos.py -q
"""
import db
import montos
import schema_v3


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "STORAGE_DIR", tmp_path / "storage")
    db.init_db()
    schema_v3.migrate()


def _lic(codigo, **campos):
    with db.conn() as c:
        db.upsert_licitacion(c, {"codigo": codigo, "nombre": campos.pop("nombre", "Módulos")})
        if campos:
            sets = ", ".join(f"{k}=?" for k in campos)
            c.execute(f"UPDATE licitaciones SET {sets} WHERE codigo=?", (*campos.values(), codigo))


def _doc(tmp_path, codigo, nombre, texto):
    p = tmp_path / nombre
    p.write_text(texto, encoding="utf-8")
    with db.conn() as c:
        c.execute("INSERT INTO documentos(codigo, nombre_archivo, ruta_local, tipo, fuente, "
                  "descargado_at) VALUES (?,?,?,?,?,?)",
                  (codigo, nombre, str(p), "txt", "local", db._now()))
    return p


# --------------------------- los dos falsos positivos ----------------------

def test_no_confunde_un_rut_con_plata():
    """CASO REAL: el RUT del municipio de Coelemu (69.150.200-7) calza exactamente con el patrón
    de un monto, y estaba a dos palabras de 'Disponibilidad Presupuestaria'."""
    t = ("Certificado de Disponibilidad Presupuestaria de la Licitación. El proveedor adjudicado "
         "deberá enviar la factura a nombre de la Ilustre Municipalidad de Coelemu, "
         "R.U.T. N° 69.150.200-7, domicilio calle Pedro León Gallo.")
    assert [c["valor"] for c in montos.candidatos(t)] == []


def test_no_confunde_un_codigo_de_cuenta_con_plata():
    """CASO REAL: de la cuenta 215.29.99.999.092.001.01.01 de Rengo se recortaba '99.999.092.001'
    (99 mil millones) y ganaba por ser el número más grande."""
    t = ("existe disponibilidad presupuestaria en la cuenta N° 215.29.99.999.092.001.01.01, "
         "para el financiamiento de adquisición de Sedes Modulares.")
    assert all(c["valor"] < 1_000_000_000 for c in montos.candidatos(t))


def test_encuentra_el_monto_aunque_el_rut_este_al_lado():
    """El RUT no puede tapar la cifra buena que está en la misma ventana."""
    t = ("La Municipalidad, R.U.T. N° 69.150.200-7, informa que el presupuesto máximo total "
         "es de $ 40.000.000 (cuarenta millones de pesos) impuesto incluido.")
    c = montos.candidatos(t)
    assert c and c[0]["valor"] == 40_000_000
    assert c[0]["en_palabras"] is True


# --------------------------- extracción normal ------------------------------

def test_lee_el_presupuesto_disponible():
    t = ("PRESUPUESTO DISPONIBLE. La presente contratación cuenta con una disponibilidad "
         "presupuestaria máxima de: $174.914.000.- (ciento setenta y cuatro millones novecientos "
         "catorce mil pesos), impuestos incluidos.")
    c = montos.candidatos(t)[0]
    assert c["valor"] == 174_914_000
    assert c["iva_incluido"] is True
    assert c["en_palabras"] is True


def test_detecta_oferta_neta():
    t = "El presupuesto máximo total es de $ 40.000.000. El precio deberá cotizarse NETO MAS IVA."
    assert montos.candidatos(t)[0]["iva_incluido"] is False


def test_ignora_cifras_fuera_de_rango():
    """Cantidades y códigos cortos no son el techo de una licitación."""
    t = "El presupuesto contempla 120.500 unidades y una superficie de 1.200.000 mm2."
    assert [c["valor"] for c in montos.candidatos(t) if c["valor"] < montos.MONTO_MIN] == []


def test_la_clave_mas_especifica_pesa_mas():
    """'presupuesto máximo' tiene que ganarle a un 'financiamiento' suelto."""
    t = ("Fuente de financiamiento: aporte de $ 5.000.000 de terceros. "
         "El presupuesto máximo total de esta licitación es de $ 90.000.000.")
    assert montos.candidatos(t)[0]["valor"] == 90_000_000


# --------------------------- sobre los documentos ---------------------------

def test_del_pliego_prefiere_la_cifra_repetida_en_varios_documentos(tmp_path, monkeypatch):
    """CASO REAL (Rengo): la misma cifra aparecía en el decreto, en los términos de requerimiento
    y en las bases. El acuerdo entre documentos es la mejor señal de que ésa es la del pliego."""
    _setup(tmp_path, monkeypatch)
    _lic("A-1-LE26")
    _doc(tmp_path, "A-1-LE26", "decreto.txt",
         "para el financiamiento de la adquisición, por un monto de $174.914.000.-")
    _doc(tmp_path, "A-1-LE26", "terminos.txt",
         "PRESUPUESTO DISPONIBLE: disponibilidad presupuestaria máxima de $174.914.000.- "
         "(ciento setenta y cuatro millones novecientos catorce mil pesos), impuestos incluidos.")
    _doc(tmp_path, "A-1-LE26", "anexo.txt",
         "El presupuesto referencial del ítem 3 asciende a la suma de $12.000.000.-")
    r = montos.del_pliego("A-1-LE26")
    assert r["monto"] == 174_914_000
    assert r["n_documentos"] == 2 and r["confianza"] == "alta"
    assert 12_000_000 in [a["valor"] for a in r["alternativas"]]


def test_del_pliego_reporta_las_alternativas(tmp_path, monkeypatch):
    """CASO REAL (JUNJI): el REX que aprueba las bases decía $97.444.000 y el ábaco $54.444.000.
    Elegir en silencio sería peor que mostrar las dos."""
    _setup(tmp_path, monkeypatch)
    _lic("B-1-LP26")
    _doc(tmp_path, "B-1-LP26", "rex.txt",
         "el presupuesto disponible para la contratación asciende a la suma de $97.444.000.- "
         "(noventa y siete millones cuatrocientos cuarenta y cuatro mil pesos) IVA INCLUIDO")
    _doc(tmp_path, "B-1-LP26", "abaco.txt",
         "Informacion Presupuestaria Monto Cierto 54.444.000 ADQUISICION, INSTALACION")
    r = montos.del_pliego("B-1-LP26")
    assert r["monto"] == 97_444_000
    assert 54_444_000 in [a["valor"] for a in r["alternativas"]]


def test_sin_documentos_devuelve_none(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _lic("C-1-LE26")
    assert montos.del_pliego("C-1-LE26") is None


def test_no_pisa_el_monto_que_vino_del_api(tmp_path, monkeypatch):
    """El API es la fuente oficial; el pliego es el respaldo para cuando falta."""
    _setup(tmp_path, monkeypatch)
    _lic("D-1-LE26", monto_estimado=50_000_000)
    _doc(tmp_path, "D-1-LE26", "bases.txt", "presupuesto máximo total de $ 99.000.000.-")
    r = montos.al_ingestar(["D-1-LE26"])
    assert r["escritos"] == []
    with db.conn() as c:
        assert c.execute("SELECT monto_estimado FROM licitaciones WHERE codigo='D-1-LE26'"
                         ).fetchone()[0] == 50_000_000


def test_al_ingestar_escribe_y_deja_traza(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _lic("E-1-LE26")
    _doc(tmp_path, "E-1-LE26", "bases.txt",
         "El presupuesto máximo total es de $ 38.558.352 (treinta y ocho millones quinientos "
         "cincuenta y ocho mil trescientos cincuenta y dos) impuesto incluido.")
    r = montos.al_ingestar(["E-1-LE26"])
    assert r["escritos"][0]["monto"] == 38_558_352
    assert r["escritos"][0]["iva_incluido"] is True
    with db.conn() as c:
        assert c.execute("SELECT monto_estimado FROM licitaciones WHERE codigo='E-1-LE26'"
                         ).fetchone()[0] == 38_558_352
        ev = c.execute("SELECT detalle FROM eventos WHERE codigo='E-1-LE26' AND tipo='monto'"
                       ).fetchone()
    assert "PLIEGO" in ev[0]


def test_un_documento_ilegible_no_frena_al_resto(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _lic("F-1-LE26")
    roto = tmp_path / "roto.pdf"
    roto.write_bytes(b"no soy un PDF")
    with db.conn() as c:
        c.execute("INSERT INTO documentos(codigo, nombre_archivo, ruta_local, tipo, fuente, "
                  "descargado_at) VALUES (?,?,?,?,?,?)",
                  ("F-1-LE26", "roto.pdf", str(roto), "pdf", "local", db._now()))
    _doc(tmp_path, "F-1-LE26", "bases.txt", "presupuesto referencial de $ 20.000.000.-")
    assert montos.del_pliego("F-1-LE26")["monto"] == 20_000_000


def test_ignora_nuestro_propio_excel_de_analisis(tmp_path, monkeypatch):
    """Mismo cuidado que en visitas.py: el Excel de análisis cita el techo del pliego."""
    _setup(tmp_path, monkeypatch)
    _lic("G-1-LE26")
    _doc(tmp_path, "G-1-LE26", "Analisis_G-1-LE26_2026-08-08.txt",
         "presupuesto máximo total de $ 777.000.000.-")
    assert montos.del_pliego("G-1-LE26") is None


# --------------------------- documento traspapelado -------------------------

def test_descarta_el_documento_de_otra_licitacion(tmp_path, monkeypatch):
    """CASO REAL: la carpeta de JUNJI ($97,4M) tenía adentro el decreto de Temuco ($22,6M).
    Sin esta guarda el extractor cargaba el techo equivocado, y con confianza."""
    _setup(tmp_path, monkeypatch)
    _lic("1575-10-LP26")
    _doc(tmp_path, "1575-10-LP26", "rex.txt",
         "el presupuesto disponible asciende a la suma de $97.444.000.- (noventa y siete millones "
         "cuatrocientos cuarenta y cuatro mil pesos) IVA INCLUIDO")
    _doc(tmp_path, "1575-10-LP26", "479_DPP_2026.txt",
         "Propuesta Pública ID 1658-171-LE26. El Presupuesto Referencial asciende a la suma de "
         "$22.650.296 Impuesto incluido.")
    r = montos.del_pliego("1575-10-LP26")
    assert r["monto"] == 97_444_000
    assert r["documentos_ajenos"] == ["479_DPP_2026.txt"]
    assert 22_650_296 not in [a["valor"] for a in r["alternativas"]]


def test_un_documento_que_cita_su_propio_id_no_es_ajeno(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _lic("3761-19-LE26")
    _doc(tmp_path, "3761-19-LE26", "decreto.txt",
         "LICITACIÓN ID 3761-19-LE26. Presupuesto máximo de $ 40.000.000.- (cuarenta millones "
         "de pesos), Impuesto IVA Incluido.")
    r = montos.del_pliego("3761-19-LE26")
    assert r["monto"] == 40_000_000 and r["documentos_ajenos"] == []


def test_un_documento_sin_ningun_id_se_considera_propio(tmp_path, monkeypatch):
    """La mayoría de los anexos no mencionan el ID: descartarlos vaciaría la extracción."""
    _setup(tmp_path, monkeypatch)
    _lic("H-1-LE26")
    _doc(tmp_path, "H-1-LE26", "anexo.txt", "El presupuesto máximo total es de $ 15.000.000.-")
    assert montos.del_pliego("H-1-LE26")["monto"] == 15_000_000


# --------------------------- el RUT tal como lo devuelve el OCR -------------

def test_rut_con_guion_largo_y_N_asterisco_del_OCR():
    """CASO REAL: el OCR devolvió 'R.U.T. N* 69.150.200—7' (em-dash y asterisco). La primera
    guarda, escrita contra el formato canónico, no disparaba sobre el documento de verdad."""
    t = ("Certificado de Disponibilidad Presupuestaria. Enviar la factura a nombre de la "
         "llustre Municipalidad de Coelemu, R.U.T. N* 69.150.200—7, domicilio calle Pedro León.")
    assert [c["valor"] for c in montos.candidatos(t)] == []


def test_rut_sin_puntos_ni_palabra_previa_igual_se_descarta_por_el_dv():
    t = "presupuesto ... la empresa 76.412.326-3 participó de la visita"
    assert [c["valor"] for c in montos.candidatos(t)] == []
