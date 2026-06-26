"""
test_asistente_safety.py — Sensor de seguridad del asistente (text-to-SQL).

El guard asistente._safe es LO ÚNICO que separa una pregunta del usuario de un
DELETE/DROP contra la base. Estos tests son adversariales: intentan colar SQL
destructivo y verifican que SIEMPRE se bloquea (devuelve None).

  python -m pytest tests/test_asistente_safety.py -q
"""
import pytest

import asistente


def test_permite_select_simple():
    assert asistente._safe("SELECT * FROM licitaciones") == "SELECT * FROM licitaciones"


def test_permite_select_con_punto_y_coma_final():
    assert asistente._safe("SELECT codigo FROM licitaciones;") == "SELECT codigo FROM licitaciones"


@pytest.mark.parametrize("sql", [
    "DELETE FROM licitaciones",
    "DROP TABLE licitaciones",
    "UPDATE licitaciones SET score_provisional=0",
    "INSERT INTO usuarios VALUES (1)",
    "ALTER TABLE x ADD COLUMN y INT",
    "CREATE TABLE x (a int)",
    "REPLACE INTO x VALUES (1)",
    "ATTACH DATABASE 'evil.db' AS e",
    "DETACH DATABASE e",
    "VACUUM",
    "PRAGMA table_info(usuarios)",
    "REINDEX",
])
def test_bloquea_sql_destructivo(sql):
    assert asistente._safe(sql) is None


def test_bloquea_query_apilada():
    """El clásico: un SELECT inofensivo seguido de ; y un DELETE."""
    assert asistente._safe("SELECT 1; DELETE FROM licitaciones") is None


def test_bloquea_keyword_destructiva_escondida():
    """Defensa en profundidad: una keyword destructiva dentro de un SELECT también se bloquea."""
    assert asistente._safe("SELECT * FROM (DROP TABLE usuarios)") is None


def test_bloquea_no_select():
    assert asistente._safe("WITH x AS (SELECT 1) SELECT * FROM x") is None  # no arranca con select
    assert asistente._safe("") is None
    assert asistente._safe(None) is None
