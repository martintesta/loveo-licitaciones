"""
relicitaciones.py — Detecta y enlaza una licitación DESIERTA con su RE-LICITACIÓN posterior.
Heurístico (no hay un campo oficial que las una):
   misma entidad compradora  +  nombre muy parecido  +  fecha de cierre posterior
→ se inserta el par en la tabla relicitaciones(codigo_desierto, codigo_nueva, score_match).

Estados MP: 7 = desierta. Candidatas a re-licitación: publicadas/cerradas/adjudicadas {5,6,8}.
"""
import re
import unicodedata
import db

_STOP = {"de","del","la","el","los","las","y","en","para","por","con","a","o","un","una",
         "adquisicion","adquisición","servicio","contratacion","contratación","suministro",
         "licitacion","licitación","publica","pública","segundo","llamado","nuevo","nueva","re"}


def _tokens(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return {t for t in re.findall(r"[a-z0-9]+", s) if len(t) > 2 and t not in _STOP}


def jaccard(a, b):
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def detectar(umbral=0.45):
    enlaces = 0
    with db.conn() as c:
        desiertas = c.execute(
            "SELECT codigo,nombre,organismo,fecha_cierre FROM licitaciones WHERE estado_mp=7").fetchall()
        for d in desiertas:
            cands = c.execute("""SELECT codigo,nombre,fecha_cierre FROM licitaciones
                                 WHERE estado_mp IN (5,6,8) AND organismo IS NOT NULL
                                   AND organismo=? AND codigo<>?
                                   AND (fecha_cierre IS NULL OR ? IS NULL OR fecha_cierre > ?)""",
                              (d["organismo"], d["codigo"], d["fecha_cierre"], d["fecha_cierre"])).fetchall()
            best, best_s = None, 0.0
            for cand in cands:
                s = jaccard(d["nombre"], cand["nombre"])
                if s > best_s:
                    best, best_s = cand, s
            if best and best_s >= umbral:
                c.execute("""INSERT INTO relicitaciones(codigo_desierto,codigo_nueva,score_match)
                             VALUES (?,?,?) ON CONFLICT(codigo_desierto,codigo_nueva)
                             DO UPDATE SET score_match=excluded.score_match""",
                          (d["codigo"], best["codigo"], round(best_s, 3)))
                db.log_evento(c, best["codigo"], "relicitacion",
                              f"re-licitación de {d['codigo']} (match {best_s:.2f})")
                enlaces += 1
    return enlaces


if __name__ == "__main__":
    # Test del núcleo (función pura) con ejemplos — no toca la base:
    a = "ADQUISICION E INSTALACION BOX DENTAL CONTAINER CESFAM LA REINA"
    b = "ADQUISICION E INSTALACION BOX DENTAL CONTAINER CESFAM LA REINA SEGUNDO LLAMADO"
    cc = "CONSTRUCCION DE PARADERO EN AVENIDA PONIENTE"
    print(f"similitud(re-licitación real)   = {jaccard(a,b):.2f}  (debe ser alta)")
    print(f"similitud(no relacionada)       = {jaccard(a,cc):.2f}  (debe ser baja)")
    # Corrida real (hoy no hay desiertas cargadas → 0 enlaces, honesto):
    print("enlaces detectados en la base    =", detectar())
