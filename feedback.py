"""
feedback.py — Loop de feedback (paso 7). Cierra el ciclo: tus correcciones mejoran el filtro.

  descartar(codigo, motivo, termino_excluir=None)
      -> estado_revision=descartada; si das un término, lo aprende como exclusión
         (se agrega a exclusiones_aprendidas.txt, que discover.py lee en cada corrida).
  aprobar(codigo, nota)
      -> estado_revision=aprobada (inicia eje de resultado en 'pendiente').
  corregir_score(codigo, score_correcto, nota)
      -> guarda feedback_humano y lo registra como evento (insumo para recalibrar Capa C).
"""
from pathlib import Path
import db

_LEARNED = Path(__file__).parent / "exclusiones_aprendidas.txt"

# Categorías de descarte. tipo='calidad' alimenta el ajuste de score (Fase 3);
# tipo='operativo' NO toca el score (señal del proceso/capacidad, no de la licitación).
# Fuente única de verdad: el frontend las recibe vía build_data -> data["categorias"].
CATEGORIAS = {
    "muy_lejos":            {"label": "Muy lejos", "tipo": "calidad"},
    "margen_bajo":          {"label": "Margen bajo", "tipo": "calidad"},
    "mal_pagador":          {"label": "Mal pagador / cash flow", "tipo": "calidad"},
    "fuera_de_core":        {"label": "Fuera de core", "tipo": "calidad"},
    "requisito_excluyente": {"label": "Requisito excluyente", "tipo": "calidad"},
    "muy_complejo":         {"label": "Muy complejo", "tipo": "calidad"},
    "visita_perdida":       {"label": "No fuimos a la visita (era buena)", "tipo": "operativo"},
    "sin_capacidad":        {"label": "Mucho trabajo / sin capacidad", "tipo": "operativo"},
    "otro":                 {"label": "Otro", "tipo": "operativo"},
}


def categorias_para_ui():
    """Lista [{k, l, tipo}] para el frontend (evita duplicar la definición en JS)."""
    return [{"k": k, "l": v["label"], "tipo": v["tipo"]} for k, v in CATEGORIAS.items()]


def aprender_exclusion(termino: str):
    termino = termino.strip().lower()
    if not termino:
        return
    existentes = set()
    if _LEARNED.exists():
        existentes = {l.strip().lower() for l in _LEARNED.read_text(encoding="utf-8").splitlines() if l.strip()}
    if termino not in existentes:
        with _LEARNED.open("a", encoding="utf-8") as f:
            f.write(termino + "\n")
        return True
    return False


def descartar(codigo, motivo, categoria=None, termino_excluir=None):
    # La tabla `descartes` la crea schema_v3.migrate(), que la app corre en cada carga
    # (build_data) antes de cualquier acción. No migramos en el hot-path del descarte.
    db.set_estado_revision(codigo, "descartada", motivo)
    cat = (categoria or "").strip().lower() or None
    tipo = CATEGORIAS.get(cat, {}).get("tipo") if cat else None
    with db.conn() as c:
        c.execute("INSERT INTO descartes(codigo, categoria, tipo, motivo, ts) VALUES (?,?,?,?,?)",
                  (codigo, cat, tipo, motivo, db._now()))
    if termino_excluir:
        if aprender_exclusion(termino_excluir):
            with db.conn() as c:
                db.log_evento(c, codigo, "feedback", f"exclusión aprendida: '{termino_excluir}'")


def aprobar(codigo, nota=""):
    db.set_estado_revision(codigo, "aprobada", nota)


def corregir_score(codigo, score_correcto, nota=""):
    with db.conn() as c:
        c.execute("UPDATE licitaciones SET feedback_humano=? WHERE codigo=?",
                  (f"score_humano={score_correcto}. {nota}", codigo))
        db.log_evento(c, codigo, "feedback", f"corrección de score -> {score_correcto}. {nota}")


if __name__ == "__main__":
    print("Exclusiones aprendidas hasta ahora:")
    print(_LEARNED.read_text(encoding="utf-8") if _LEARNED.exists() else "(ninguna)")
