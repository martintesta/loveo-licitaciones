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


def descartar(codigo, motivo, termino_excluir=None):
    db.set_estado_revision(codigo, "descartada", motivo)
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
