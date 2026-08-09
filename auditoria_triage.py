"""
auditoria_triage.py — Contrasta el embudo nuevo contra las decisiones humanas ya registradas.

Es la única validación honesta disponible: no hay resultados de licitación (0 ganadas/perdidas),
pero sí hay 33 descartes con su motivo. Eso alcanza para medir lo que importa del Gate 1:
  · ¿mata lo que el humano descartó por "fuera de core"?      (verdaderos positivos)
  · ¿deja vivo lo que el humano mantuvo o descartó por otra razón? (falsos positivos = lo caro)

Un falso positivo del embudo (matar algo que Loveo sí quería) cuesta una licitación.
Un falso negativo (dejar pasar basura) cuesta horas de análisis. La asimetría manda: ante la duda
el embudo tiene que dejar pasar, y por eso se reporta cada caso, no sólo el agregado.

  python auditoria_triage.py
"""
import sys

import db
import triage


def correr(verbose=True):
    with db.conn() as c:
        filas = [dict(r) for r in c.execute("SELECT * FROM licitaciones")]
        cats = {r["codigo"]: r["categoria"] for r in c.execute("SELECT codigo, categoria FROM descartes")}

    fuera_core = {k for k, v in cats.items() if v == "fuera_de_core"}
    otro_motivo = {k for k, v in cats.items() if v and v != "fuera_de_core"}

    aciertos, escapes, falsos_pos, mata_ok = [], [], [], []
    for lic in filas:
        r = triage.gate_producto(lic)
        cod = lic["codigo"]
        if cod in fuera_core:
            (aciertos if not r["pasa"] else escapes).append((cod, lic["nombre"], r))
        elif cod in otro_motivo or lic["estado_revision"] in ("en_revision", "aprobada"):
            # el humano lo consideró producto de Loveo (lo descartó por plata/visita, o sigue vivo)
            (falsos_pos if not r["pasa"] else mata_ok).append((cod, lic["nombre"], r))

    n_core = len(fuera_core)
    n_loveo = len(falsos_pos) + len(mata_ok)
    print("=" * 96)
    print("AUDITORÍA DEL GATE 1 contra las decisiones humanas ya registradas")
    print("=" * 96)
    print(f"\nDescartadas por el humano como 'fuera de core': {n_core}")
    print(f"   el embudo también las mata : {len(aciertos):3d}  ({100*len(aciertos)//max(n_core,1)}%)")
    print(f"   se le escapan              : {len(escapes):3d}   <- costo: horas de análisis")
    print(f"\nConsideradas producto de Loveo por el humano: {n_loveo}")
    print(f"   el embudo las deja pasar   : {len(mata_ok):3d}  ({100*len(mata_ok)//max(n_loveo,1)}%)")
    print(f"   el embudo las MATA         : {len(falsos_pos):3d}   <- costo: licitación perdida")

    if verbose and falsos_pos:
        print("\n" + "!" * 96)
        print("FALSOS POSITIVOS — el embudo mata algo que el humano sí quería. Revisar uno por uno:")
        print("!" * 96)
        for cod, nom, r in falsos_pos:
            print(f"  {cod:20s} [{r['senal']}] {r['motivo'][:56]}")
            print(f"  {'':20s} {str(nom)[:88]}")
    if verbose and escapes:
        print("\n" + "-" * 96)
        print("ESCAPES — basura que el embudo deja pasar (barato, pero dice qué regla falta):")
        print("-" * 96)
        for cod, nom, r in escapes:
            print(f"  {cod:20s} [{r['senal']}] {str(nom)[:66]}")

    with db.conn() as c:
        total = len(filas)
    muertas = sum(1 for lic in filas if not triage.gate_producto(lic)["pasa"])
    print(f"\nSobre las {total} licitaciones de la base: el embudo descarta {muertas} "
          f"({100*muertas//max(total,1)}%) en el Gate 1, sin leer un solo PDF.")
    return {"aciertos": len(aciertos), "escapes": len(escapes),
            "falsos_positivos": len(falsos_pos), "ok": len(mata_ok)}


if __name__ == "__main__":
    sys.exit(0 if correr() else 0)
