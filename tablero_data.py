"""
tablero_data.py — Arma el DATA (licitaciones + grupos + meta) que consume el tablero.

Único punto de lectura de loveo.db para las vistas del tablero. Lo usan tanto el tablero
read-only (tablero2) como el tablero con acciones (tablero3 / componente bidireccional).
"""
import json
import datetime
from collections import Counter
import db
import textnorm
from textnorm import na as _na  # normalización compartida (una sola fuente de verdad)
import schema_v3
import competencia
import keywords as kwmod
import aprendizaje
import recall
import comprador
import worker
import cubicacion_ia
import plan

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
         "Septiembre", "Octubre", "Noviembre", "Diciembre"]
MESES_AB = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]
CATEGORIAS = [
    ("Contenedor", ["container", "conteiner", "contenedor"]),
    ("Modular/Sala", ["modulo", "modular", "prefabricad", "sala", "oficina"]),
    ("Baños", ["bano"]),
    ("REAS/RESPEL", ["reas", "respel", "suspel"]),
    ("Box dental/vet", ["box"]),
    ("Panel solar", ["panel solar", "paneles solares"]),
]
DIM_ORDER = [("margen", "Margen"), ("complejidad", "Complejidad"), ("logistico", "Logístico"),
             ("cashflow", "Cash flow"), ("alineacion", "Alineación"), ("repetibilidad", "Repetibilidad")]
ESTADO_LBL = {"nueva": "Nueva", "en_revision": "En revisión", "aprobada": "Aprobada",
              "descartada": "Descartada", "pendiente": "Pendiente", "presentada": "Presentada",
              "ganada": "Ganada", "perdida": "Perdida", "desierta": "Desierta"}


def _parse(dt):
    if not dt:
        return None
    s = str(dt).replace("Z", "").strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    return None


def _clp(v):
    return "$" + f"{v:,.0f}".replace(",", ".") if v else "—"


def _region_corta(region):
    return textnorm.region_corta(region) or "—"   # misma lógica compartida + fallback de UI


def _lista(v):
    """Fuerza a lista: el LLM a veces devuelve un string donde esperamos una lista → iterar ese
    string daría CARACTERES sueltos. list→tal cual, string no vacío→[string], resto→[]."""
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v.strip():
        return [v.strip()]
    return []


def _garantias(gar):
    """Normaliza la lista de garantías de la extracción (dicts {tipo, monto_o_pct} o strings) a texto."""
    out = []
    for g in _lista(gar)[:8]:
        if isinstance(g, dict):
            tipo = str(g.get("tipo") or "garantía").strip()
            val = g.get("monto_o_pct") or g.get("monto") or g.get("pct")
            out.append(f"{tipo}: {val}" if val else tipo)
        elif g:
            out.append(str(g))
    return out


def _dims(sj):
    out = []
    for k, lbl in DIM_ORDER:
        dv = (sj.get("dimensiones") or {}).get(k)
        if dv:
            out.append({"n": lbl, "score": dv.get("score"), "nota": dv.get("nota", ""), "ev": bool(dv.get("evaluado"))})
    return out


_INIT_DONE = set()


def _ensure_init():
    """migrate() + backfill() son setup/mantenimiento. Correrlos en CADA build_data (cada
    carga de página y cada acción) contra Neon cross-continente es carísimo: el DDL de migrate
    son decenas de statements × latencia EE.UU.↔SA. Se corren UNA vez por proceso y por base
    (clave = DATABASE_URL o ruta sqlite). Un nuevo deploy reinicia el proceso y los re-corre.
    Tests: cada base temporal es una clave distinta, así que igual migran."""
    key = db.DATABASE_URL or str(db.DB_PATH)
    if key in _INIT_DONE:
        return
    schema_v3.migrate()
    try:
        import kwstats
        kwstats.backfill()
    except Exception:
        pass
    _INIT_DONE.add(key)


def _seguro(etiqueta, fn, default):
    """Ejecuta un bloque OPCIONAL de build_data sin que su falla mate el tablero.

    Un error acá es PERMANENTE (la app no carga nunca, en ninguna pantalla), a diferencia de una
    acción, que solo rompe ese click. Se loguea a observabilidad y se degrada al default: el panel
    correspondiente queda vacío, pero el resto del tablero funciona."""
    try:
        return fn()
    except Exception as e:
        try:
            import observabilidad
            observabilidad.capturar(f"build_data.{etiqueta}", e)
        except Exception:
            pass
        return default


def build_data(usuario=None):
    _ensure_init()  # migrate + backfill: una vez por proceso/base, NO en cada carga
    now = datetime.datetime.now()
    year = now.year
    with db.conn() as c:
        # Columnas explícitas, NO 'SELECT *': json_detalle es el ~72% del peso de la tabla (blobs de
        # varios KB por fila) y acá solo se necesita saber si está vacío → se pide como flag.
        raw = [dict(r) for r in c.execute(
            "SELECT codigo, nombre, organismo, region, monto_estimado, moneda, fecha_cierre, "
            "       fecha_visita, estado_mp, descripcion, admisible, admisible_motivo, "
            "       vigente_oferta, estado_revision, estado_resultado, score_provisional, "
            "       score_json, fecha_descubierta, fecha_actualizada, "
            "       (json_detalle IS NULL) AS sin_detalle "
            "FROM licitaciones").fetchall()]
        eventos = {}
        for e in c.execute("SELECT codigo, ts, tipo, detalle FROM eventos ORDER BY ts").fetchall():
            eventos.setdefault(e["codigo"], []).append({"ts": e["ts"], "tipo": e["tipo"], "det": e["detalle"]})
        docs = {}
        for d in c.execute("SELECT id, codigo, nombre_archivo, ruta_local, tipo, url, fuente FROM documentos").fetchall():
            docs.setdefault(d["codigo"], []).append({
                "id": d["id"], "nombre": d["nombre_archivo"], "url": d["url"] or d["ruta_local"],
                "fuente": d["fuente"] or d["tipo"] or "doc",
            })
        analisis = {}
        for a in c.execute("SELECT codigo, ts, resumen, presupuesto_clp, plazo_dias, json_extraccion "
                           "FROM analisis_bases "
                           "WHERE id IN (SELECT MAX(id) FROM analisis_bases GROUP BY codigo)").fetchall():
            ex = {}
            if a["json_extraccion"]:
                try:
                    ex = json.loads(a["json_extraccion"])
                except (ValueError, TypeError):
                    ex = {}
            # requisitos SIN truncar: perder uno en silencio es justo lo que esto busca evitar.
            analisis[a["codigo"]] = {"ts": a["ts"], "resumen": a["resumen"],
                                     "presupuesto": _clp(a["presupuesto_clp"]), "plazo": a["plazo_dias"],
                                     "garantias": _garantias(ex.get("garantias")),
                                     "requisitos": [str(x) for x in _lista(ex.get("requisitos_clave"))]}
        # Cubicación asistida (borrador IA, Fase 1): BOM por licitación, en una sola query.
        cubic_ia = {}
        for ci in c.execute(
                "SELECT cu.codigo AS codigo, ci.partida, ci.grupo, ci.descripcion, ci.cantidad, "
                "ci.unidad, ci.precio_unitario, ci.total, ci.precio_fuente, ci.precio_url "
                "FROM cubicaciones cu JOIN cubicacion_items ci ON ci.cubicacion_id = cu.id "
                "WHERE cu.origen='ia' ORDER BY cu.codigo, ci.id").fetchall():
            cubic_ia.setdefault(ci["codigo"], []).append(
                {"partida": ci["partida"], "grupo": ci["grupo"], "descripcion": ci["descripcion"],
                 "cantidad": ci["cantidad"], "unidad": ci["unidad"],
                 "precio": ci["precio_unitario"], "total": ci["total"],
                 "fuente": ci["precio_fuente"], "url": ci["precio_url"]})
        # Recetas por tipo de producto (Fase 5): cuántas partidas hay por tipo, para ofrecer pre-llenar.
        recetas_n = {rr["proyecto"]: rr["n"] for rr in c.execute(
            "SELECT cu.proyecto AS proyecto, COUNT(ci.id) AS n FROM cubicaciones cu "
            "JOIN cubicacion_items ci ON ci.cubicacion_id = cu.id "
            "WHERE cu.origen='receta' GROUP BY cu.proyecto").fetchall()}

    lics, order = {}, []
    groups = {"cierran": [], "nuevas": [], "fitAnio": [], "siguiendo": [], "cierran5": [], "nuevas7d": []}
    for nombre, _ in CATEGORIAS:
        groups["cat:" + nombre] = []
    for ph in ["Nuevas", "En revisión", "Aprobadas", "Presentadas", "Cerradas"]:
        groups["emb:" + ph] = []
    for i in range(12):
        groups["mes:" + str(i)] = []

    for r in raw:
        cod = r["codigo"]
        order.append(cod)
        rev, res = r["estado_revision"], r["estado_resultado"]
        desc = _parse(r["fecha_descubierta"])
        cierre = _parse(r["fecha_cierre"])
        sj = {}
        if r["score_json"]:
            try:
                sj = json.loads(r["score_json"])
            except ValueError:
                sj = {}
        # días de CALENDARIO (no timedelta.days, que trunca por 24h): así el tablero, el plan y el
        # email (alertas.dias_hasta) dicen todos lo mismo. Antes: cierre mañana 08:00 → "cierra HOY".
        dias = (cierre.date() - now.date()).days if cierre else None
        _vis = _parse(r["fecha_visita"])                        # visita a terreno (para el plan del día)
        estado_lbl = ESTADO_LBL.get(res) if res and res != "pendiente" else ESTADO_LBL.get(rev, rev)
        _dd = _dims(sj)  # confianza: cuántas de las 6 dimensiones están realmente evaluadas
        _tp = cubicacion_ia.tipo_producto(r["nombre"] or "")  # tipo de producto (para recetas, Fase 5)

        lics[cod] = {
            "cod": cod, "nom": r["nombre"] or "—", "org": r["organismo"] or "",
            "reg": r["region"] or "", "regc": _region_corta(r["region"]),
            "monto": _clp(r["monto_estimado"]), "moneda": r["moneda"] or "",
            "cierreFmt": cierre.strftime("%d-%m-%Y %H:%M") if cierre else "", "dias": dias,
            "visita": (_vis.strftime("%d-%m-%Y %H:%M") if _vis else ""),
            # días a la visita en días de calendario; si la hora de hoy ya pasó, -1 (no accionable).
            "diasVisita": (None if not _vis else (-1 if _vis < now else (_vis.date() - now.date()).days)),
            "estMp": r["estado_mp"], "estRev": rev, "estRes": res, "estadoLbl": estado_lbl,
            "adm": bool(r["admisible"]), "admMot": r["admisible_motivo"] or "", "vig": bool(r["vigente_oferta"]),
            "desc": (desc.strftime("%d-%m-%Y") if desc else ""), "score": r["score_provisional"],
            "tri": sj.get("triage"), "reqBases": bool(sj.get("requiere_bases")), "dims": _dd,
            "evDims": sum(1 for d in _dd if d["ev"]), "nDims": len(_dd) or 6,
            "evalPts": sj.get("evaluable_pts"),
            "descr": (r["descripcion"] or "")[:1200], "eventos": eventos.get(cod, []),
            "docs": docs.get(cod, []), "analisis": analisis.get(cod),
            "cubicIA": cubic_ia.get(cod, []),  # borrador de cubicación asistida (Fase 1)
            "recetaDisp": ({"tipo": _tp, "n": recetas_n[_tp]} if _tp and _tp in recetas_n else None),
            "tipoProd": _tp,  # tipo de producto (para el boost de preferencia del plan, Fase 3)
            "incompleto": bool(r["sin_detalle"]),  # no se bajó el detalle (solo código+nombre)
        }

        if rev != "descartada":
            if res in ("ganada", "perdida", "desierta"):
                groups["emb:Cerradas"].append(cod)
            elif res == "presentada":
                groups["emb:Presentadas"].append(cod)
            elif rev == "aprobada":
                groups["emb:Aprobadas"].append(cod)
            elif rev == "en_revision":
                groups["emb:En revisión"].append(cod)
            else:
                groups["emb:Nuevas"].append(cod)
        if desc and desc.year == year:
            groups["fitAnio"].append(cod)
            groups["mes:" + str(desc.month - 1)].append(cod)
        if desc and (now - desc).days <= 7:
            groups["nuevas7d"].append(cod)
        if rev in ("en_revision", "aprobada"):
            groups["siguiendo"].append(cod)
        if dias is not None and dias >= 0:
            if dias <= 5:
                groups["cierran5"].append(cod)
            if dias <= 7 and rev != "descartada":
                groups["cierran"].append(cod)
        if rev == "nueva":
            groups["nuevas"].append(cod)
        n = _na(r["nombre"])
        for nombre, terms in CATEGORIAS:
            if any(t in n for t in terms):
                groups["cat:" + nombre].append(cod)

    groups["cierran"].sort(key=lambda x: lics[x]["dias"])
    groups["nuevas"].sort(key=lambda x: lics[x]["desc"], reverse=True)

    # Ajuste asistido por descartes/resultados (Fases 3/B): 1 lectura, se aplica por lic (display-only).
    _ap = _seguro("aprendizaje", aprendizaje.cargar, {})
    _rep = _seguro("comprador", comprador.reputaciones, {})  # reputación de pago (Ficha Comprador manual)
    for _l in lics.values():
        _l["ajuste"] = aprendizaje.ajuste_lic(_ap, _l["reg"], _l["org"])
        rp = _rep.get(_l["org"])
        _l["repPago"] = ({"nivel": rp["nivel"], "nota": rp["nota"] or ""} if rp else None)
        _al = comprador.alerta_para(rp)
        if _al:  # heads-up proactivo; el penalty numérico lo pone el descarte, no se duplica acá
            _l["ajuste"]["alertas"].append(_al)

    # --- Inteligencia / oportunidades (panel del Inicio) ---
    desiertas = [{"cod": l["cod"], "nom": l["nom"], "regc": l["regc"]}
                 for l in lics.values() if l.get("estMp") == 7][:6]
    competidores = []
    try:
        for r in competencia.resumen(limite=6):   # el top se acota en SQL, no materializando todo
            competidores.append({"razon": r["razon_social"], "part": r["participaciones"], "ganadas": r["ganadas"]})
    except Exception:
        competidores = []
    adjudic = []
    try:
        with db.conn() as c:
            for r in c.execute(
                "SELECT i.nombre_producto p, i.nombre_proveedor g, i.monto_total m, a.n_oferentes o "
                "FROM items i JOIN adjudicaciones a ON a.codigo=i.codigo "
                "WHERE i.rut_proveedor IS NOT NULL ORDER BY a.fecha DESC LIMIT 6"
            ).fetchall():
                adjudic.append({"producto": r["p"] or "—", "ganador": r["g"] or "—",
                                "monto": _clp(r["m"]), "oferentes": r["o"]})
    except Exception:
        adjudic = []
    intel = {"desiertas": desiertas, "competidores": competidores, "adjudicaciones": adjudic}

    # --- Métricas de uso y valor (trazabilidad propia, $0) ---
    rev_c = Counter(r["estado_revision"] for r in raw)
    res_c = Counter(r["estado_resultado"] for r in raw if r["estado_resultado"] and r["estado_resultado"] != "pendiente")
    ev_tipo, actividad = Counter(), Counter()
    for lst in eventos.values():
        for e in lst:
            ev_tipo[e["tipo"]] += 1
            actividad[(e["ts"] or "")[:10]] += 1
    ganadas, perdidas = res_c.get("ganada", 0), res_c.get("perdida", 0)
    win_rate = round(100 * ganadas / (ganadas + perdidas)) if (ganadas + perdidas) else None
    monto_ganado = sum((r["monto_estimado"] or 0) for r in raw if r["estado_resultado"] == "ganada")
    today = now.date()
    dias14 = [(today - datetime.timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
    metricas = {
        "eventos_total": int(sum(ev_tipo.values())),
        "aprobadas": rev_c.get("aprobada", 0), "descartadas": rev_c.get("descartada", 0),
        "en_revision": rev_c.get("en_revision", 0), "nuevas": rev_c.get("nueva", 0),
        "revisadas": rev_c.get("aprobada", 0) + rev_c.get("descartada", 0),
        "capac": ev_tipo.get("capa_c", 0), "docs": ev_tipo.get("documento", 0),
        "feedback": ev_tipo.get("feedback", 0) + ev_tipo.get("nota", 0),
        "fit_anio": len(groups["fitAnio"]), "total_lic": len(raw),
        "presentadas": res_c.get("presentada", 0), "ganadas": ganadas, "perdidas": perdidas,
        "desiertas_res": res_c.get("desierta", 0), "win_rate": win_rate, "monto_ganado": _clp(monto_ganado),
        "actividad": [{"dia": d[8:10] + "/" + d[5:7], "n": actividad.get(d, 0)} for d in dias14],
    }

    try:
        import kwstats
        kw_perf = kwstats.stats()  # backfill ya corrió en _ensure_init (1 vez por proceso)
        kws = kwmod.listar()
        for k in kws:
            s = kw_perf.get(k["termino"])
            if s:
                k.update(s)
    except Exception:
        kws = []

    _acts = [a for a in (_parse(r["fecha_actualizada"]) for r in raw) if a]
    actualizado = max(_acts).strftime("%d-%m-%Y %H:%M") if _acts else ""
    return {
        "lics": lics, "order": order, "groups": groups, "intel": intel, "metricas": metricas,
        "keywords": kws,
        "actualizado": actualizado,
        # paneles opcionales: si uno falla se degrada (vacío) en vez de matar TODO el tablero
        "aprendizaje": _seguro("aprendizaje.resumen", lambda: aprendizaje.resumen(_ap), {}),
        "recall": _seguro("recall", recall.auditar, {}),
        "worker": _seguro("worker", worker.salud, {}),
        # plan del día, priorizado y sesgado por lo que ESTE usuario efectivamente ataca (Fase 3/4)
        "plan": _seguro("plan", lambda: plan.construir(lics, prefs=plan.preferencias(usuario)), []),
        "meta": {
            "year": year, "monthsShown": (now.month if year == now.year else 12),
            "mesAb": MESES_AB, "meses": MESES,
            "embOrder": ["Nuevas", "En revisión", "Aprobadas", "Presentadas", "Cerradas"],
            "embColors": {"Nuevas": "#94A3B8", "En revisión": "#F59E0B", "Aprobadas": "#0E7490",
                          "Presentadas": "#047857", "Cerradas": "#475569"},
            "catOrder": [n for n, _ in CATEGORIAS],
        },
    }
