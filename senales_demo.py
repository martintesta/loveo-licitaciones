"""
senales_demo.py — Enfoque A (puente en consola) SIN PARPADEO, vía componente bidireccional.

El triage (Seguir / Descartar + nota con sugerencias) vive dentro del look consola; al confirmar,
el componente devuelve el valor a Python por el protocolo de Streamlit → se escribe en loveo.db →
re-render suave del componente con datos frescos (NO recarga la página).

Mejoras pedidas:
  - Seguir y Descartar piden un motivo, con chips sugeridos (título, título+monto, monto,
    nuevo nicho, estudio de mercado, otros) editables.
  - Todo tabulado en columnas fijas (alineado).
  - Score en círculo verde oscuro; hover muestra las razones (desglose de dimensiones).

Acciones REVERSIBLES (cambian estado_revision). "↺ Restaurar demo" deshace lo tocado.

  streamlit run senales_demo.py
"""
import os
import json
import streamlit as st
import streamlit.components.v1 as components
import db

st.set_page_config(page_title="Señales — triage", layout="wide")
st.markdown("<style>.block-container{padding-top:2rem;max-width:1080px}</style>", unsafe_allow_html=True)
db.init_db()
st.session_state.setdefault("touched", set())
st.session_state.setdefault("last_nonce", None)
st.session_state.setdefault("flash", "")

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "components", "senales")
_senales = components.declare_component("loveo_senales", path=_DIR)

_DIM_ORDER = [("margen", "Margen"), ("complejidad", "Complejidad"), ("logistico", "Logístico"),
              ("cashflow", "Cash flow"), ("alineacion", "Alineación"), ("repetibilidad", "Repetibilidad")]


def _sj(s):
    if not s:
        return {}
    try:
        return json.loads(s)
    except ValueError:
        return {}


def _dims(sj):
    out = []
    for k, lbl in _DIM_ORDER:
        dv = (sj.get("dimensiones") or {}).get(k)
        if dv:
            out.append({"n": lbl, "score": dv.get("score"), "nota": dv.get("nota", ""), "ev": bool(dv.get("evaluado"))})
    return out


def _regc(r):
    for p in ("Región de la ", "Región del ", "Región de ", "Región "):
        if r and r.startswith(p):
            return r[len(p):]
    return r or "—"


def build_items():
    with db.conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT codigo, nombre, region, score_provisional, score_json "
            "FROM licitaciones WHERE estado_revision='nueva' ORDER BY fecha_descubierta DESC"
        ).fetchall()]
    items = []
    for r in rows:
        sj = _sj(r["score_json"])
        items.append({"cod": r["codigo"], "nom": r["nombre"] or "—", "reg": _regc(r["region"]),
                      "score": r["score_provisional"], "triage": sj.get("triage"), "dims": _dims(sj)})
    return items


st.title("Señales — bandeja de triage")
cols = st.columns([4, 1])
cols[0].caption("Seguir/Descartar abren el motivo con sugerencias. El score está en círculo verde oscuro; "
                "pasá el mouse por encima para ver por qué tiene ese puntaje. Se guarda sin recargar la página.")
if cols[1].button("↺ Restaurar demo", use_container_width=True):
    if st.session_state.touched:
        with db.conn() as cc:
            for cod in st.session_state.touched:
                cc.execute("UPDATE licitaciones SET estado_revision='nueva' WHERE codigo=?", (cod,))
        st.session_state.touched = set()
    st.session_state.flash = "↺ Restaurado: lo tocado volvió a 'nueva'."
    st.rerun()

if st.session_state.flash:
    st.success(st.session_state.flash)
    st.session_state.flash = ""

items = build_items()
val = _senales(data={"items": items}, key="senales", default=None)

if isinstance(val, dict) and val.get("nonce") and val["nonce"] != st.session_state.last_nonce:
    st.session_state.last_nonce = val["nonce"]
    act, cod, nota = val.get("act"), val.get("cod"), (val.get("nota") or "")
    if cod:
        if act == "seguir":
            db.set_estado_revision(cod, "en_revision", "seguir. " + nota)
            st.session_state.flash = f"✓ Seguís {cod}" + (f" · {nota}" if nota else "")
        elif act == "descartar":
            db.set_estado_revision(cod, "descartada", nota or "descartada")
            st.session_state.flash = f"🗑 Descartada {cod}" + (f" · {nota}" if nota else "")
        st.session_state.touched.add(cod)
    st.rerun()
