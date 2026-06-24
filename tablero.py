"""
tablero.py — Tablero local de loveo-licitaciones (Streamlit), conectado a las tablas reales.

  pip install streamlit pandas
  streamlit run tablero.py

Pestañas:
  Pipeline                 — lista + score Atlas + documentos + feedback
  Tablero                  — Kanban por estado (versión Streamlit, "mover a" en vez de arrastrar)
  Inteligencia competitiva — adjudicaciones + items reales (ganador / precio / oferentes)
  Desiertas                — estado_mp=7 + enlace de re-licitación
  Seguimiento Competencia  — competencia.resumen() / ficha / facturado por año
  Asistente IA             — Nivel 1 (text-to-SQL) — pendiente de API key

Local-first: lee el mismo SQLite que el pipeline. Sin data inventada: si una tabla está vacía,
la vista lo dice (hay que correr el pipeline con tu ticket).
"""
import json
import pandas as pd
import streamlit as st
import db, feedback, competencia

st.set_page_config(page_title="Loveo Licitaciones", layout="wide")
db.init_db()

TRIAGE = {"Priorizar": "🟢", "Revisar": "🟡", "Descartar candidato": "🔴"}
CLP = lambda v: f"${v:,.0f}" if v not in (None, "") else "—"

with db.conn() as c:
    run = c.execute("SELECT fecha, candidatos, admisibles FROM runs ORDER BY ts DESC LIMIT 1").fetchone()
st.title("Loveo Licitaciones")
if run:
    st.caption(f"Última corrida: día {run['fecha']} · {run['candidatos']} candidatos · {run['admisibles']} admisibles")

tab_pipe, tab_board, tab_intel, tab_des, tab_seg, tab_ia = st.tabs(
    ["Pipeline", "Tablero", "Inteligencia competitiva", "Desiertas", "Seguimiento de Competencia", "Asistente IA"]
)

# ===================== PIPELINE =====================
with tab_pipe:
    cfa, cfb, cfc = st.columns([2, 1, 1])
    rev = cfa.multiselect("Estado de revisión", sorted(db.REVISION_STATES), default=["nueva", "en_revision"])
    solo_admis = cfb.checkbox("Solo admisibles", value=True)
    solo_vig = cfc.checkbox("Solo vigentes", value=False)

    q = "SELECT * FROM licitaciones WHERE 1=1"; params = []
    if rev:
        q += f" AND estado_revision IN ({','.join('?'*len(rev))})"; params += rev
    if solo_admis: q += " AND admisible=1"
    if solo_vig:   q += " AND vigente_oferta=1"
    q += " ORDER BY score_provisional DESC NULLS LAST, fecha_descubierta DESC"
    with db.conn() as c:
        filas = c.execute(q, params).fetchall()

    st.subheader(f"{len(filas)} licitaciones")
    for f in filas:
        sc = f["score_provisional"]
        sj = json.loads(f["score_json"]) if f["score_json"] else None
        triage = sj["triage"] if sj else "—"
        badge = TRIAGE.get(triage, "⚪")
        with st.expander(f"{badge}  {f['codigo']} · {f['nombre'][:70]}  ·  {sc if sc is not None else '—'}/120 · {triage}"):
            c1, c2 = st.columns([2, 1])
            with c1:
                st.markdown(f"**Organismo:** {f['organismo'] or '—'}")
                st.markdown(f"**Región:** {f['region'] or '—'}")
                st.markdown(f"**Monto estimado:** {CLP(f['monto_estimado'])} {f['moneda'] or ''}")
                st.markdown(f"**Cierre:** {f['fecha_cierre'] or '—'} · **Visita:** {f['fecha_visita'] or '—'}")
                st.markdown(f"**Admisibilidad:** {f['admisible_motivo'] or '—'}")
                if sj:
                    st.markdown("**Desglose del score provisional:**")
                    for dn, dv in sj["dimensiones"].items():
                        pend = "" if dv["evaluado"] else "  ⏳ *pendiente bases*"
                        st.markdown(f"- {dn}: **{dv['score']}/10** — {dv['nota']}{pend}")
                    if sj.get("requiere_bases"):
                        st.info("Score PROVISIONAL. El GO/NO-GO final requiere bases + cubicación (Capa C).")
            with c2:
                st.markdown("**Documentos**")
                with db.conn() as c:
                    docs = c.execute("SELECT nombre_archivo, ruta_local FROM documentos WHERE codigo=?", (f["codigo"],)).fetchall()
                if not docs:
                    st.caption(f"Sin documentos (estado: {f['docs_estado']}). Correr download.py local.")
                for d in docs:
                    try:
                        with open(d["ruta_local"], "rb") as fh:
                            st.download_button(f"⬇ {d['nombre_archivo']}", fh.read(),
                                               file_name=d["nombre_archivo"], key=f"dl_{f['codigo']}_{d['nombre_archivo']}")
                    except Exception:
                        st.caption(f"(no encontrado: {d['nombre_archivo']})")
                st.divider()
                st.markdown("**Feedback**")
                if st.button("✅ Aprobar", key=f"ap_{f['codigo']}"):
                    feedback.aprobar(f["codigo"]); st.rerun()
                motivo = st.text_input("Motivo descarte", key=f"mo_{f['codigo']}")
                termino = st.text_input("Término a excluir", key=f"te_{f['codigo']}")
                if st.button("🗑 Descartar", key=f"de_{f['codigo']}"):
                    feedback.descartar(f["codigo"], motivo or "descartada", termino or None); st.rerun()

# ===================== TABLERO (Kanban) =====================
with tab_board:
    st.caption("Kanban sobre la máquina de estados. En Streamlit el avance es por botón “mover a”, no arrastrando.")
    with db.conn() as c:
        rows = c.execute("SELECT codigo,nombre,region,score_provisional,estado_revision,estado_resultado,score_json FROM licitaciones").fetchall()

    def fase(r):
        if r["estado_revision"] == "descartada": return None
        if r["estado_resultado"] in ("ganada", "perdida", "desierta"): return "Cerradas"
        if r["estado_resultado"] == "presentada": return "Presentadas"
        if r["estado_revision"] == "aprobada": return "Aprobadas"
        if r["estado_revision"] == "en_revision": return "En revisión"
        return "Nuevas"

    cols = {"Nuevas": [], "En revisión": [], "Aprobadas": [], "Presentadas": [], "Cerradas": []}
    for r in rows:
        f = fase(r)
        if f: cols[f].append(r)

    cc = st.columns(5)
    for col, (name, items) in zip(cc, cols.items()):
        col.markdown(f"**{name}**  ·  {len(items)}")
        for r in items:
            sc = r["score_provisional"]
            sj = json.loads(r["score_json"]) if r["score_json"] else None
            badge = TRIAGE.get(sj["triage"], "⚪") if sj else "⚪"
            with col.container(border=True):
                st.markdown(f"{badge} `{r['codigo']}`  ·  **{sc if sc is not None else '—'}**")
                st.caption(f"{r['nombre'][:60]}")
                if r["region"]: st.caption(r["region"])

# ===================== INTELIGENCIA COMPETITIVA =====================
with tab_intel:
    st.subheader("Adjudicaciones — quién gana, a qué precio, con cuántos oferentes")
    with db.conn() as c:
        adj = c.execute("""
            SELECT i.codigo, i.nombre_producto AS producto, l.organismo,
                   i.nombre_proveedor AS ganador, i.monto_unitario, i.monto_total,
                   a.n_oferentes, a.fecha
            FROM items i
            JOIN adjudicaciones a ON a.codigo=i.codigo
            LEFT JOIN licitaciones l ON l.codigo=i.codigo
            WHERE i.rut_proveedor IS NOT NULL
            ORDER BY a.fecha DESC
        """).fetchall()
    if not adj:
        st.info("Sin adjudicaciones extraídas todavía. Corré el pipeline con tu ticket (trae el bloque Adjudicación) "
                "y se llena solo vía extract.py.")
    else:
        df = pd.DataFrame([dict(r) for r in adj])
        df["monto_unitario"] = df["monto_unitario"].map(CLP)
        df["monto_total"] = df["monto_total"].map(CLP)
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption(f"{len(adj)} ítems adjudicados. Señal: 1 oferente = baja competencia. "
                   "Producto fuera de tu core (ej. vigas) = falso positivo a descartar.")

# ===================== DESIERTAS =====================
with tab_des:
    st.subheader("Licitaciones desiertas — el 25% sin adjudicar")
    with db.conn() as c:
        des = c.execute("""
            SELECT l.codigo, l.nombre, l.organismo, l.region, l.monto_estimado, l.fecha_cierre,
                   r.codigo_nueva, r.score_match
            FROM licitaciones l
            LEFT JOIN relicitaciones r ON r.codigo_desierto=l.codigo
            WHERE l.estado_mp=7
            ORDER BY l.fecha_cierre DESC
        """).fetchall()
    if not des:
        st.info("Sin desiertas cargadas todavía. Aparecen cuando el pipeline detecte estado_mp=7. "
                "Las re-licitaciones se enlazan solas (relicitaciones.detectar).")
    else:
        data = []
        for r in des:
            data.append({
                "Código desierto": r["codigo"], "Nombre": (r["nombre"] or "")[:55],
                "Organismo": r["organismo"], "Región": r["region"],
                "Monto est.": CLP(r["monto_estimado"]), "Cierre": r["fecha_cierre"],
                "Re-licitación": f"↻ {r['codigo_nueva']} (match {r['score_match']})" if r["codigo_nueva"] else "Sin republicar — oportunidad",
            })
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

# ===================== SEGUIMIENTO DE COMPETENCIA =====================
with tab_seg:
    st.subheader("Seguimiento de Competencia")
    res = competencia.resumen()
    if not res:
        st.info("Sin competidores todavía. Se reconstruyen de las adjudicaciones (extract.py) al correr el pipeline.")
    else:
        tabla = [{
            "Razón social": r["razon_social"], "RUT": r["rut"], "Contacto": r["contacto"] or "— (vía API)",
            "Particip.": r["participaciones"], "Ganadas": r["ganadas"], "Perdidas": r["perdidas"],
            "Facturado total": CLP(r["facturado_total"]),
        } for r in res]
        st.dataframe(pd.DataFrame(tabla), use_container_width=True, hide_index=True)
        st.caption("‘Perdidas’ requiere las ofertas públicas tras apertura (futuro). "
                   "‘Facturado’ usa el monto adjudicado como proxy.")

        opciones = {f"{r['razon_social']} ({r['rut']})": r["rut"] for r in res}
        sel = st.selectbox("Ver ficha de competidor", list(opciones.keys()))
        if sel:
            fpa = competencia.facturado_por_anio(opciones[sel])
            if fpa:
                st.markdown("**Facturado por año (Mercado Público)**")
                st.bar_chart(pd.DataFrame({"Facturado": {str(k): v for k, v in fpa.items()}}))
            else:
                st.caption("Sin facturación por año registrada aún.")

# ===================== ASISTENTE IA =====================
with tab_ia:
    st.subheader("Asistente IA")
    st.info("**Nivel 1 (text-to-SQL sobre tu base)** — pendiente de configurar tu API key de Anthropic. "
            "Una vez lista, vas a poder preguntar en lenguaje natural: vencimientos, conteos, scores, "
            "ganadores y precios, y se responde desde estas mismas tablas. "
            "Nivel 2 (mercado, web) y Nivel 3 (contenido de bases, requiere Capa B+C) vienen después.")
    st.text_input("Preguntá… (deshabilitado hasta conectar la API)", disabled=True)
