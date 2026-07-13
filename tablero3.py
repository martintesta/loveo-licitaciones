"""
tablero3.py — Tablero Loveo Construcciones, consola bidireccional (con acciones, sin parpadeo).

La consola entera (rail + Inicio + Señales + Listado + Radar + ficha) vive en UN componente
bidireccional (components/console). La navegación/drill-down es JS instantáneo; las acciones que
escriben en loveo.db (seguir / aprobar / descartar + nota, marcar resultado) hacen un round-trip
suave: el componente devuelve el valor, Python escribe y re-renderiza con datos frescos — sin recargar.

  streamlit run tablero3.py

Reemplaza a tablero2.py (read-only) sumándole las acciones. Local-first, nada inventado.
"""
import os
import hashlib
import datetime
import streamlit as st
import streamlit.components.v1 as components
import extra_streamlit_components as stx

# La API key vive en el entorno de USUARIO (Windows). Si el server arrancó sin ella, la leemos del registro.
if not os.environ.get("ANTHROPIC_API_KEY"):
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as _k:
            _v, _ = winreg.QueryValueEx(_k, "ANTHROPIC_API_KEY")
            if _v:
                os.environ["ANTHROPIC_API_KEY"] = _v
    except Exception:
        pass

import db
import feedback
import tablero_data
import drive
import asistente
import capac_score
import keywords
import usuarios
import recall
import comprador
import cubicacion_ia
import observabilidad

st.set_page_config(page_title="Loveo Construcciones", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
  #MainMenu, header, footer {visibility:hidden;}
  [data-testid="stHeader"], [data-testid="stDecoration"] {display:none;}
  .block-container {padding:0 !important; max-width:100% !important;}
  [data-testid="stAppViewContainer"] {background:#EBEEF1;}
  iframe {border:none; width:100% !important;}
</style>
""", unsafe_allow_html=True)

db.init_db()
observabilidad.init()   # Sentry si hay SENTRY_DSN (no-op sin DSN)
st.session_state.setdefault("last_nonce", None)
st.session_state.setdefault("user", None)

# ---- Gate de login con sesión persistente (cookie + token en la base) ----
usuarios.seed_if_empty()
_cm = stx.CookieManager(key="loveo_cm")
_tok = _cm.get("loveo_tok")
if not st.session_state.user and _tok:
    _su = usuarios.validar_sesion(_tok)
    if _su:
        st.session_state.user = _su
        st.session_state.tok = _tok

if not st.session_state.user:
    if not st.session_state.get("cookie_checked"):
        # primera pasada: dejar que la cookie se lea antes de mostrar el login
        st.session_state.cookie_checked = True
        st.markdown("<div style='margin:12vh auto;text-align:center;color:#69727E'>Verificando sesión…</div>",
                    unsafe_allow_html=True)
        st.stop()
    st.markdown("<div style='max-width:380px;margin:9vh auto 0'>", unsafe_allow_html=True)
    st.markdown("### Loveo Construcciones")
    st.caption("Ingresá con tu usuario.")
    with st.form("login"):
        _u = st.text_input("Usuario")
        _p = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Entrar", use_container_width=True):
            _usr = usuarios.verify(_u, _p)
            if _usr:
                _newtok = usuarios.crear_sesion(_usr["username"])
                _cm.set("loveo_tok", _newtok,
                        expires_at=datetime.datetime.now() + datetime.timedelta(days=usuarios.SESSION_DAYS))
                st.session_state.user = _usr
                st.session_state.tok = _newtok
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "components", "console")
_console = components.declare_component("loveo_console", path=_DIR)

data = tablero_data.build_data()
data["flash"] = st.session_state.pop("flash", "")
data["chat"] = st.session_state.get("chat", [])
data["pending_capac"] = st.session_state.get("pending_capac", {})
data["user"] = st.session_state.user
data["categorias"] = feedback.categorias_para_ui()
data["categorias_resultado"] = feedback.categorias_resultado_para_ui()
data["errores"] = observabilidad.recientes(8)   # errores capturados sin resolver (panel de salud)
val = _console(data=data, key="console", default=None)

if isinstance(val, dict) and val.get("nonce") and val["nonce"] != st.session_state.last_nonce:
    st.session_state.last_nonce = val["nonce"]
    act = val.get("act")
    cod = val.get("cod")
    nota = (val.get("nota") or "").strip()
    if act == "ask":
        q = (val.get("question") or "").strip()
        if q:
            try:
                if q.startswith("/"):
                    ans, sql = keywords.comando(q), ""
                else:
                    res = asistente.ask(q)
                    ans, sql = res.get("answer", ""), res.get("sql", "")
            except Exception as e:
                ans, sql = f"Error: {e}", ""
            chat = st.session_state.get("chat", [])
            chat.append({"q": q, "a": ans, "sql": sql})
            st.session_state.chat = chat[-20:]
    elif act == "kw_add":
        term = (val.get("termino") or "").strip()
        tipo = val.get("tipo") or "incluir"
        if term:
            keywords.add(term, tipo, origen="manual")
            st.session_state.flash = f"Keyword agregada: '{term}' ({tipo})."
    elif act == "kw_toggle":
        kid = val.get("kid")
        on = str(val.get("on")) == "1"
        if kid:
            keywords.set_activo(kid, on)
            st.session_state.flash = "Keyword " + ("activada." if on else "desactivada.")
    elif act == "logout":
        usuarios.borrar_sesion(st.session_state.get("tok"))
        try:
            _cm.delete("loveo_tok")
        except Exception:
            pass
        st.session_state.user = None
        st.session_state.tok = None
    elif act == "add_codigo":
        codigo = (val.get("codigo") or "").strip()
        if codigo:
            import run_daily
            r = run_daily.procesar_codigo(codigo)
            if r.get("ok"):
                est = "admisible" if r.get("admisible") else "no admisible"
                sc = f" · score {r['score']}" if r.get("score") is not None else ""
                ya = " (ya estaba, actualizada)" if r.get("ya_existia") else ""
                st.session_state.flash = f"✓ Agregada {r['codigo']} — {est}{sc}.{ya}"
            else:
                st.session_state.flash = r.get("error", "No se pudo agregar.")
    elif act == "rep_pago":
        nivel = val.get("nivel")
        org = (val.get("org") or "").strip()
        if not org and cod:  # resolver el organismo desde la licitación
            with db.conn() as c:
                r = c.execute("SELECT organismo FROM licitaciones WHERE codigo=?", (cod,)).fetchone()
                org = (r["organismo"] or "").strip() if r else ""
        if org and nivel in comprador.NIVELES:
            comprador.set_reputacion(org, nivel, nota)
            st.session_state.flash = f"✓ Reputación de '{org}': {comprador.NIVEL_LABEL[nivel]}."
    elif act == "cubic_ia":
        if cod:
            r = cubicacion_ia.generar(cod)
            st.session_state.flash = (f"✓ Borrador de cubicación: {len(r['items'])} partidas."
                                      if r.get("ok") else r.get("error", "No se pudo generar."))
    elif act == "cubic_guardar":
        if cod:
            r = cubicacion_ia.guardar_borrador(cod, val.get("items") or [])
            st.session_state.flash = (f"✓ Cubicación curada: {len(r['items'])} partidas."
                                      if r.get("ok") else r.get("error", "No se pudo guardar."))
    elif act == "cubic_preciar":
        if cod:
            r = cubicacion_ia.preciar(cod)
            st.session_state.flash = (
                f"✓ Preciado: {r['preciados']} partidas ({r['web']} por web). Costo ≈ ${r['costo']:,.0f}."
                .replace(",", ".") if r.get("ok") else r.get("error", "No se pudo preciar."))
    elif act == "error_resuelto":
        eid = val.get("eid")
        if eid:
            observabilidad.resolver(eid)
            st.session_state.flash = "Error marcado como resuelto."
    elif act == "cubic_receta":
        if cod:
            r = cubicacion_ia.prellenar_desde_receta(cod)
            st.session_state.flash = (
                f"✓ Pre-llenado desde receta '{r['tipo']}': {len(r['items'])} partidas. Ajustá y guardá."
                if r.get("ok") else r.get("error", "No se pudo pre-llenar."))
    elif act == "cubic_margen":
        if cod:
            r = cubicacion_ia.margen(cod)
            if not r.get("ok"):
                st.session_state.flash = r.get("error", "No se pudo calcular el margen.")
            elif r.get("aplicado"):
                st.session_state.flash = (
                    f"✓ Margen {r['margen_pct']}% (costo ${r['costo']:,.0f} vs techo ${r['techo']:,.0f}). "
                    f"Score {r['score_antes']}→{r['score_despues']}.".replace(",", "."))
            else:
                st.session_state.flash = (
                    f"Margen estimado {r['margen_pct']}% (parcial). Faltan {r['sin_precio']} precios "
                    "para aplicarlo al score.")
    elif act == "recall":
        rcod = (val.get("cod") or "").strip()
        acc = val.get("accion")
        if rcod and len(rcod) <= 20 and acc in ("promovida", "descartada"):
            recall.resolver(rcod, acc)
            st.session_state.flash = (f"✓ {rcod} marcada relevante — copiala al alta manual del Listado."
                                      if acc == "promovida" else f"Descartada del recall: {rcod}.")
    elif cod and act:
        if act == "seguir":
            db.set_estado_revision(cod, "en_revision", "seguir. " + nota)
        elif act == "aprobar":
            feedback.aprobar(cod, nota)
        elif act == "descartar":
            feedback.descartar(cod, nota or "descartada", categoria=val.get("categoria"))
        elif act.startswith("resultado:"):
            feedback.marcar_resultado(cod, act.split(":", 1)[1], categoria=val.get("categoria"), motivo=nota)
        elif act == "capac":
            est = capac_score.estimar(cod)
            if not est["ok"]:
                st.session_state.flash = est["error"]
            else:
                pend = st.session_state.get("pending_capac", {})
                pend[cod] = {"tokens": est["tokens"]}
                st.session_state.pending_capac = pend
                st.session_state.flash = f"≈{est['tokens']} tokens de entrada (modelo Haiku, costo bajo). Confirmá para analizar."
        elif act == "capac_run":
            r = capac_score.analizar(cod)
            pend = st.session_state.get("pending_capac", {})
            pend.pop(cod, None)
            st.session_state.pending_capac = pend
            st.session_state.flash = (f"✓ Bases analizadas. Score {r['score_antes']}→{r['score_despues']}."
                                      if r.get("ok") else r.get("error", "Error en el análisis."))
        elif act == "capac_cancel":
            pend = st.session_state.get("pending_capac", {})
            pend.pop(cod, None)
            st.session_state.pending_capac = pend
        elif act == "doc_link":
            url = (val.get("url") or "").strip()
            nombre = (val.get("nombre") or "").strip() or (url.split("/")[-1] or "Documento (Drive)")
            if url:
                with db.conn() as c:
                    c.execute("""INSERT OR IGNORE INTO documentos
                                 (codigo, nombre_archivo, ruta_local, tipo, url, fuente, sha256, descargado_at)
                                 VALUES (?,?,?,?,?,?,?,?)""",
                              (cod, nombre, url, "drive", url, "drive",
                               hashlib.sha256(url.encode("utf-8")).hexdigest(), db._now()))
                    db.log_evento(c, cod, "documento", f"link Drive agregado: {nombre}")
        elif act == "doc_del":
            docid = val.get("docid")
            if docid:
                with db.conn() as c:
                    c.execute("DELETE FROM documentos WHERE id=? AND codigo=?", (docid, cod))
                    db.log_evento(c, cod, "documento", "documento quitado")
        elif act == "doc_sync":
            url = (val.get("url") or "").strip()
            if not drive.disponible():
                st.session_state.flash = "Conectá Google Drive primero (ver SETUP_DRIVE.md) y reintentá."
            elif url:
                try:
                    files = drive.sync_link(url, os.path.join("storage", cod))
                    with db.conn() as c:
                        for f in files:
                            view = f"https://drive.google.com/file/d/{f['id']}/view"
                            c.execute("""INSERT OR IGNORE INTO documentos
                                         (codigo, nombre_archivo, ruta_local, tipo, url, fuente, sha256, descargado_at)
                                         VALUES (?,?,?,?,?,?,?,?)""",
                                      (cod, f["name"], f["path"], f["mime"], view, "drive",
                                       hashlib.sha256(f["id"].encode("utf-8")).hexdigest(), db._now()))
                        db.log_evento(c, cod, "documento", f"Drive sincronizado: {len(files)} archivo(s)")
                    st.session_state.flash = f"✓ {len(files)} archivo(s) sincronizados desde Drive."
                except Exception as e:
                    st.session_state.flash = f"Error leyendo Drive: {e}"
    st.rerun()
