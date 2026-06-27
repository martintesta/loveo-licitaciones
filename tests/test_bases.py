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
