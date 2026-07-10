"""
keywords.py — Keywords como DATOS (editables desde la app), no en código.

Reemplaza las listas hardcodeadas: la fuente de verdad del descubrimiento son las filas de la
tabla `keywords` (tipo incluir/excluir/amplio, activo). Se siembra una vez desde config_local.

  seed_if_empty()       — si la tabla está vacía, la puebla desde config_local (KEYWORDS_INCLUIR/EXCLUIR/AMPLIO).
  listar(tipo, activo)  — filas para la vista.
  add(termino, tipo)    — agrega (idempotente por (termino, tipo)).
  set_activo(id, on)    — activa/desactiva.
  get_active_lists()    — (incluir, excluir, amplio) ACTIVAS, para discover/filters.
"""
import os
import json
import db
import schema_v3
from textnorm import na as _na, pat as _pat  # normalización compartida (una sola fuente de verdad)


def seed_if_empty():
    schema_v3.migrate()
    with db.conn() as c:
        n = c.execute("SELECT COUNT(*) FROM keywords").fetchone()[0]
        if n:
            return 0
    try:
        import config_local as cfg
        inc = list(getattr(cfg, "KEYWORDS_INCLUIR", getattr(cfg, "KEYWORDS", [])) or [])
        exc = list(getattr(cfg, "KEYWORDS_EXCLUIR", getattr(cfg, "EXCLUSIONES", [])) or [])
        amp = list(getattr(cfg, "KEYWORDS_AMPLIO", []) or [])
    except Exception:
        inc, exc, amp = [], [], []
    # exclusiones aprendidas por feedback (archivo) → entran como excluir/aprendida
    try:
        from pathlib import Path
        f = Path(__file__).parent / "exclusiones_aprendidas.txt"
        if f.exists():
            for t in f.read_text(encoding="utf-8").splitlines():
                t = t.strip()
                if t and not t.startswith("#"):
                    exc.append(t)
    except Exception:
        pass
    added = 0
    with db.conn() as c:
        for term in inc:
            added += _ins(c, term, "incluir", "seed")
        for term in exc:
            added += _ins(c, term, "excluir", "seed")
        for term in amp:
            added += _ins(c, term, "amplio", "seed")
    return added


def _ins(c, termino, tipo, origen):
    termino = (termino or "").strip()
    if not termino:
        return 0
    c.execute("INSERT OR IGNORE INTO keywords(termino, tipo, origen, activo, creado_at) VALUES (?,?,?,1,?)",
              (termino, tipo, origen, db._now()))
    return 1


def add(termino, tipo="incluir", origen="manual", nota=""):
    seed_if_empty()
    with db.conn() as c:
        c.execute("INSERT OR IGNORE INTO keywords(termino, tipo, origen, activo, nota, creado_at) VALUES (?,?,?,1,?,?)",
                  ((termino or "").strip(), tipo, origen, nota, db._now()))


def set_activo(kid, on):
    with db.conn() as c:
        c.execute("UPDATE keywords SET activo=? WHERE id=?", (1 if on else 0, kid))


def listar(tipo=None, activo=None):
    seed_if_empty()
    q = "SELECT id, termino, tipo, origen, activo, nota FROM keywords WHERE 1=1"
    p = []
    if tipo:
        q += " AND tipo=?"; p.append(tipo)
    if activo is not None:
        q += " AND activo=?"; p.append(1 if activo else 0)
    q += " ORDER BY tipo, termino"
    with db.conn() as c:
        return [dict(r) for r in c.execute(q, p).fetchall()]


def get_active_lists():
    seed_if_empty()
    inc, exc, amp = [], [], []
    with db.conn() as c:
        for r in c.execute("SELECT termino, tipo FROM keywords WHERE activo=1").fetchall():
            (inc if r["tipo"] == "incluir" else exc if r["tipo"] == "excluir" else amp).append(r["termino"])
    return inc, exc, amp


# ------------------------------------------------------------------ evaluación IA + comandos /kw
def _juzgar(termino, n, ejemplos):
    """Clasifica un término con IA (core/relacionado/ruido). Degrada a heurística sin API key."""
    try:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("no key")
        import anthropic
        cl = anthropic.Anthropic(api_key=key)
        msg = cl.messages.create(
            model=os.environ.get("LOVEO_MODEL", "claude-haiku-4-5"), max_tokens=200,
            system=("Sos analista de Loveo Construcciones (construcción modular en acero: containers, módulos, "
                    "baños/salas modulares, REAS/RESPEL, paneles solares; NO vigas/puentes/jardinería/vehículos/"
                    "laboratorios). Clasificá un término de búsqueda para licitaciones de Mercado Público. "
                    "Devolvé SOLO JSON {\"tipo\":\"incluir|amplio|excluir|skip\",\"razon\":\"una frase corta\"}."),
            messages=[{"role": "user", "content": f'Término: "{termino}". Matchea {n} licitaciones históricas. '
                                                   f'Ejemplos: {ejemplos}. ¿incluir (core), amplio (relacionado, a '
                                                   f'vigilar), excluir (ruido/fuera de core) o skip (irrelevante)?'}])
        raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        d = json.loads(raw)
        return d.get("tipo", "incluir"), d.get("razon", "")
    except Exception:
        return ("incluir" if n > 0 else "amplio"), (
            "matchea histórico (heurística sin IA)" if n > 0 else "sin matches históricos; entra como amplio para vigilar")


def evaluar(termino):
    termino = (termino or "").strip()
    pat = _pat(termino)
    with db.conn() as c:
        nombres = [r["nombre"] for r in c.execute("SELECT nombre FROM licitaciones").fetchall()]
    matches = [nm for nm in nombres if pat.search(_na(nm))]
    tipo, razon = _juzgar(termino, len(matches), [m[:50] for m in matches[:3]])
    return {"matches": len(matches), "ejemplos": matches[:3], "tipo": tipo, "razon": razon}


_HELP = ("Comandos de keywords:\n"
         "• /kw eval <término> — evalúa (matches históricos + IA), sin agregar\n"
         "• /kw add <término> — evalúa y agrega como lo recomiende la IA\n"
         "• /kw add-incluir|add-excluir|add-amplio <término> — agrega forzado\n"
         "• /kw list — resumen de keywords activas")


def comando(text):
    parts = (text or "").strip().split()
    if len(parts) < 2 or parts[1] in ("help", "ayuda"):
        return _HELP
    sub = parts[1].lower()
    termino = " ".join(parts[2:]).strip()
    if sub == "list":
        inc, exc, amp = get_active_lists()
        return f"Keywords activas — incluir: {len(inc)}, excluir: {len(exc)}, amplio: {len(amp)}.\nIncluir: {', '.join(inc[:20])}"
    if sub.startswith("add-"):
        tipo = sub.split("-", 1)[1]
        if tipo not in ("incluir", "excluir", "amplio") or not termino:
            return "Uso: /kw add-incluir <término> (o add-excluir / add-amplio)."
        add(termino, tipo, origen="manual")
        return f"✓ '{termino}' agregado como {tipo} (forzado)."
    if sub in ("eval", "add"):
        if not termino:
            return f"Uso: /kw {sub} <término>"
        ev = evaluar(termino)
        cab = f'"{termino}": {ev["matches"]} matches históricos'
        if ev["ejemplos"]:
            cab += f' (ej: {ev["ejemplos"][0][:50]}…)'
        if sub == "eval":
            return f'🔍 {cab}.\nRecomendación IA: **{ev["tipo"]}** — {ev["razon"]}'
        if ev["tipo"] == "skip":
            return f'⏭ {cab}.\nNo lo agregué: {ev["razon"]}. Si igual querés: /kw add-incluir {termino}'
        add(termino, ev["tipo"], origen="sugerida", nota=ev["razon"])
        return f'✓ Agregado "{termino}" como **{ev["tipo"]}** — {ev["razon"]} ({ev["matches"]} matches históricos).'
    return "Comando no reconocido. Probá /kw help"
