"""
tablero2.py — Rediseño v2 del tablero (PASO 1+): chasis consola + Inicio + drill-down.

Estética "consola" (rail oscuro) del spec docs/rediseno_dashboard.md, en Streamlit:
Streamlit hace de backend (lee loveo.db) e inyecta TODOS los datos en una plantilla HTML
de alta fidelidad. La navegación (drill-down) y la ficha individual se renderizan en el
cliente, así no hay que salir de la herramienta para ver una licitación.

  streamlit run tablero2.py

Interacción:
  - Todo es clickeable: KPIs, filas, embudo, categorías, meses → abren un listado filtrado.
  - Una licitación abre su FICHA individual (datos, score, admisibilidad, trazabilidad) dentro de la app.
  - Desde la ficha se puede seguir profundizando (región/organismo) y SIEMPRE hay botón "← Volver".

Local-first, nada inventado. Las pantallas Señales/Listado/Radar/Mapa/Inteligencia/Asistente
son placeholders 'en construcción' (próximos pasos, en Streamlit nativo para las de acción).
"""
import json
import datetime
import unicodedata
import streamlit as st
import streamlit.components.v1 as components
import db

st.set_page_config(page_title="Loveo Construcciones", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
  #MainMenu, header, footer {visibility:hidden;}
  [data-testid="stHeader"], [data-testid="stDecoration"] {display:none;}
  .block-container {padding:0 !important; max-width:100% !important;}
  [data-testid="stAppViewContainer"] {background:#EBEEF1;}
  iframe {border:none;}
</style>
""", unsafe_allow_html=True)

db.init_db()

NOW = datetime.datetime.now()
YEAR = NOW.year
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


def _na(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


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
    if not region:
        return "—"
    for p in ("Región de la ", "Región del ", "Región de ", "Región "):
        if region.startswith(p):
            return region[len(p):]
    return region


def _dims(sj):
    out = []
    for k, lbl in DIM_ORDER:
        dv = (sj.get("dimensiones") or {}).get(k)
        if dv:
            out.append({"n": lbl, "score": dv.get("score"), "nota": dv.get("nota", ""),
                        "ev": bool(dv.get("evaluado"))})
    return out


# ------------------------------------------------------------------ datos reales
with db.conn() as c:
    raw = [dict(r) for r in c.execute("SELECT * FROM licitaciones").fetchall()]
    eventos = {}
    for e in c.execute("SELECT codigo, ts, tipo, detalle FROM eventos ORDER BY ts").fetchall():
        eventos.setdefault(e["codigo"], []).append({"ts": e["ts"], "tipo": e["tipo"], "det": e["detalle"]})

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
    dias = (cierre - NOW).days if cierre else None
    estado_lbl = ESTADO_LBL.get(res) if res and res != "pendiente" else ESTADO_LBL.get(rev, rev)

    lics[cod] = {
        "cod": cod, "nom": r["nombre"] or "—", "org": r["organismo"] or "",
        "reg": r["region"] or "", "regc": _region_corta(r["region"]),
        "monto": _clp(r["monto_estimado"]), "moneda": r["moneda"] or "",
        "cierreFmt": cierre.strftime("%d-%m-%Y %H:%M") if cierre else "", "dias": dias,
        "visita": (_parse(r["fecha_visita"]).strftime("%d-%m-%Y %H:%M") if _parse(r["fecha_visita"]) else ""),
        "estMp": r["estado_mp"], "estRev": rev, "estRes": res, "estadoLbl": estado_lbl,
        "adm": bool(r["admisible"]), "admMot": r["admisible_motivo"] or "", "vig": bool(r["vigente_oferta"]),
        "desc": (desc.strftime("%d-%m-%Y") if desc else ""), "score": r["score_provisional"],
        "tri": sj.get("triage"), "reqBases": bool(sj.get("requiere_bases")), "dims": _dims(sj),
        "descr": (r["descripcion"] or "")[:1200], "eventos": eventos.get(cod, []),
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
    if desc and desc.year == YEAR:
        groups["fitAnio"].append(cod)
        groups["mes:" + str(desc.month - 1)].append(cod)
    if desc and (NOW - desc).days <= 7:
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

DATA = {
    "lics": lics, "order": order, "groups": groups,
    "meta": {
        "year": YEAR, "monthsShown": (NOW.month if YEAR == NOW.year else 12),
        "mesAb": MESES_AB, "meses": MESES,
        "embOrder": ["Nuevas", "En revisión", "Aprobadas", "Presentadas", "Cerradas"],
        "embColors": {"Nuevas": "#94A3B8", "En revisión": "#F59E0B", "Aprobadas": "#0E7490",
                      "Presentadas": "#047857", "Cerradas": "#475569"},
        "catOrder": [n for n, _ in CATEGORIAS],
    },
}

# ------------------------------------------------------------------ estilos
STYLE = """
:root{--mono:'JetBrains Mono',ui-monospace,monospace;--disp:'Montserrat',system-ui,sans-serif;--body:'Inter',system-ui,sans-serif;}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;margin:0;overflow:hidden}
body{font-family:var(--body);font-size:13.5px;color:#0F1216;background:#EBEEF1;-webkit-font-smoothing:antialiased}
.app{display:grid;grid-template-columns:178px 1fr;height:100%}
.rail{background:#0E1115;color:#fff;display:flex;flex-direction:column;padding:14px 11px;overflow:auto}
.brand{display:flex;align-items:center;gap:9px;padding:2px 4px 13px;border-bottom:1px solid #252B33;margin-bottom:11px}
.mark{width:24px;height:24px;border-radius:4px;background:#0E7490;display:flex;align-items:center;justify-content:center;font-weight:600;font-size:14px;color:#fff;flex:none}
.bname{font-family:var(--disp);font-size:15px;font-weight:700}
.bsub{font-family:var(--mono);font-size:9px;color:#7C8793;letter-spacing:.6px;margin-top:1px}
.grp{font-family:var(--mono);font-size:9px;color:#7C8793;letter-spacing:1.4px;padding:8px 7px 5px}
.item{display:flex;align-items:center;gap:10px;padding:8px 9px;border-radius:4px;color:#BFC7D0;font-size:12.5px;cursor:pointer;border:none;background:none;width:100%;text-align:left;position:relative;margin-bottom:1px;font-family:var(--body)}
.item:hover{background:#191D23;color:#fff}
.item.on{background:#191D23;color:#fff}
.item.on::before{content:"";position:absolute;left:0;top:6px;bottom:6px;width:3px;background:#F59E0B;border-radius:2px}
.item .ic{width:17px;flex:none;color:#7C8793;display:flex}
.item.on .ic{color:#F59E0B}
.item .bdg{margin-left:auto;background:#F59E0B;color:#0E1115;font-family:var(--mono);font-weight:700;font-size:10px;border-radius:3px;padding:1px 6px}
.who{margin-top:auto;display:flex;align-items:center;gap:9px;padding:9px;border-radius:4px;background:#191D23;border:1px solid #252B33}
.who .av{width:26px;height:26px;border-radius:4px;background:#0E7490;display:flex;align-items:center;justify-content:center;font-weight:600;font-size:11px;flex:none}
.who .wn{font-size:11.5px}.who .wr{font-family:var(--mono);font-size:9px;color:#7C8793}
.main{display:flex;flex-direction:column;background:#EBEEF1;overflow:hidden}
.topbar{background:#fff;border-bottom:0.5px solid #C4CAD2;height:48px;display:flex;align-items:center;gap:12px;padding:0 18px;flex:none}
.crumb{font-family:var(--mono);font-size:10.5px;color:#9AA2AC;letter-spacing:.5px}
.crumb b{color:#0F1216}
.search{margin-left:6px;flex:1;max-width:300px;display:flex;align-items:center;gap:8px;background:#EBEEF1;border:0.5px solid #D8DCE2;border-radius:4px;padding:7px 11px}
.search input{border:none;background:none;outline:none;flex:1;font-size:12.5px;color:#0F1216;font-family:var(--body)}
.live{margin-left:auto;font-family:var(--mono);font-size:10.5px;color:#333B43;display:flex;align-items:center;gap:6px;border:0.5px solid #D8DCE2;border-radius:4px;padding:5px 10px;background:#F7F8FA}
.dot{width:7px;height:7px;border-radius:50%;background:#F59E0B;display:inline-block}
.scroll{overflow:auto;padding:18px;flex:1}
.eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:1.4px;color:#69727E}
.h1{font-family:var(--disp);font-size:19px;font-weight:800;color:#0F1216;margin-top:3px}
.sec{display:flex;align-items:center;gap:8px;margin:18px 0 9px}
.sec .ic{display:flex}.sec .t{font-family:var(--mono);font-size:11px;letter-spacing:.5px;color:#0F1216;font-weight:600;cursor:pointer}
.sec .t:hover{color:#155E75}
.col{display:flex;flex-direction:column;gap:7px}
.crow{background:#fff;border:0.5px solid #D8DCE2;border-radius:0 4px 4px 0;padding:10px 13px;display:flex;align-items:center;gap:11px;cursor:pointer}
.crow:hover{background:#F7F8FA}
.crow .nm{font-size:12.5px;color:#0F1216;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.crow .rg{font-size:11px;color:#69727E;white-space:nowrap}
.code{font-family:var(--mono);font-size:11px;color:#155E75;font-weight:500;text-decoration:none}
.diaschip{font-family:var(--mono);font-size:11px;font-weight:500;border-radius:3px;padding:2px 7px;white-space:nowrap}
.pill{font-family:var(--mono);font-size:10px;border-radius:3px;padding:2px 8px;white-space:nowrap}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:#D8DCE2;border:0.5px solid #D8DCE2;border-radius:4px;overflow:hidden;margin-top:16px}
.kpi{background:#fff;padding:11px 13px;cursor:pointer}
.kpi:hover{background:#F7F8FA}
.kpi .l{font-family:var(--mono);font-size:9px;letter-spacing:.7px;color:#69727E}
.kpi .n{font-family:var(--disp);font-size:23px;font-weight:800;margin-top:5px;line-height:1}
.panel{background:#fff;border:0.5px solid #D8DCE2;border-radius:4px;padding:13px 15px}
.plabel{font-family:var(--mono);font-size:10px;letter-spacing:.6px;color:#155E75;font-weight:600;margin-bottom:11px}
.cols2{display:grid;grid-template-columns:1.3fr 1fr;gap:13px;margin-top:16px}
.bar{flex:1;display:flex;flex-direction:column;align-items:center;gap:4px;justify-content:flex-end;cursor:pointer}
.bar:hover .bc{opacity:.7}
.catrow{display:grid;grid-template-columns:104px 1fr 22px;align-items:center;gap:9px;margin-bottom:6px;cursor:pointer}
.catrow:hover{opacity:.7}
.fstage{display:grid;grid-template-columns:104px 1fr 24px;align-items:center;gap:10px;margin-bottom:6px;cursor:pointer}
.fstage:hover{opacity:.7}
.fl{font-family:var(--mono);font-size:10.5px;color:#333B43}
.fbar,.catbar{height:16px;background:#E7EAEF;border-radius:2px;overflow:hidden}
.catbar{height:9px;border-radius:3px}
.fc{font-family:var(--mono);font-size:11px;font-weight:500;text-align:right}
.ph{background:#fff;border:1px dashed #C4CAD2;border-radius:4px;padding:40px;text-align:center;color:#69727E;font-family:var(--mono);font-size:12px;margin-top:20px}
.ph b{color:#0F1216}
.backbtn{font-family:var(--mono);font-size:11px;color:#333B43;background:#fff;border:0.5px solid #D8DCE2;border-radius:4px;padding:7px 13px;cursor:pointer;display:inline-flex;align-items:center;gap:7px;margin-bottom:14px}
.backbtn:hover{border-color:#94A3B8;color:#0F1216}
.dsub{font-family:var(--mono);font-size:11px;color:#69727E;margin-top:4px}
.tbl{background:#fff;border:0.5px solid #D8DCE2;border-radius:4px;overflow:hidden;margin-top:13px}
.thead,.lrow{display:grid;grid-template-columns:1.1fr 2.2fr 1fr 0.9fr 0.5fr 0.9fr;gap:10px;padding:10px 14px;align-items:center}
.thead{background:#F2F4F6;border-bottom:0.5px solid #C4CAD2}
.thead span{font-family:var(--mono);font-size:9px;letter-spacing:.7px;color:#69727E}
.lrow{border-bottom:0.5px solid #E7EAEF;cursor:pointer}
.lrow:last-child{border-bottom:none}.lrow:hover{background:#F7F8FA}
.lnom{font-size:12.5px;color:#0F1216;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.lreg{font-size:11px;color:#69727E}.lcie{font-family:var(--mono);font-size:11px;color:#333B43}
.lsc{font-family:var(--mono);font-size:12px;font-weight:500;text-align:right;color:#155E75}
.empty{font-family:var(--mono);font-size:12px;color:#9AA2AC;background:#fff;border:1px dashed #C4CAD2;border-radius:4px;padding:30px;text-align:center;margin-top:13px;line-height:1.6}
.filters{display:flex;gap:9px;flex-wrap:wrap;margin:14px 0 4px}
.fbox{flex:1;min-width:180px;display:flex;align-items:center;gap:8px;background:#fff;border:0.5px solid #D8DCE2;border-radius:4px;padding:7px 11px}
.fbox .fic{font-family:var(--mono);font-size:13px;color:#69727E;display:flex}
.fbox input{border:none;outline:none;background:none;flex:1;font-size:12.5px;color:#0F1216;font-family:var(--body)}
.fhead{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;flex-wrap:wrap;background:#fff;border:0.5px solid #D8DCE2;border-radius:4px;padding:16px 18px;margin-bottom:13px}
.badges{display:flex;gap:6px;margin-top:9px;flex-wrap:wrap}
.badge{font-family:var(--mono);font-size:9.5px;color:#333B43;background:#F1EFE8;border-radius:3px;padding:3px 8px;text-transform:uppercase}
.badge.adm{color:#085041;background:#E1F5EE}
.verdict{text-align:right}.vk{font-family:var(--mono);font-size:9px;letter-spacing:.6px;color:#69727E}
.vv{font-family:var(--disp);font-size:22px;font-weight:800;color:#155E75;margin-top:3px}.vv span{font-size:12px;color:#9AA2AC;font-weight:400}
.vx{font-family:var(--mono);font-size:9.5px;color:#B45309;margin-top:3px}
.card{background:#fff;border:0.5px solid #D8DCE2;border-radius:4px;padding:14px 16px;margin-bottom:11px}
.ct{font-family:var(--mono);font-size:10px;letter-spacing:.6px;color:#155E75;font-weight:600;margin-bottom:11px}
.meta{display:grid;grid-template-columns:1fr 1fr;gap:10px 18px}
.mk{font-family:var(--mono);font-size:9px;letter-spacing:.4px;color:#69727E;text-transform:uppercase}
.mv{font-size:12.5px;color:#0F1216;font-weight:500;margin-top:2px}
.mv.lnk{color:#155E75;cursor:pointer;text-decoration:underline;text-decoration-color:#9FE1CB}
.dim{display:grid;grid-template-columns:120px 1fr 30px;align-items:center;gap:10px;margin-bottom:8px}
.dl{font-size:11.5px;color:#333B43}.dl .pend{font-family:var(--mono);font-size:9px;color:#92400E;background:#FAEEDA;border-radius:3px;padding:1px 5px;margin-left:4px}
.track{height:9px;background:#E7EAEF;border-radius:3px;overflow:hidden}
.fill{height:100%;background:#0E7490;border-radius:3px}
.fill.pend{background:repeating-linear-gradient(45deg,#FCD9A0,#FCD9A0 5px,#FBE7C4 5px,#FBE7C4 10px)}
.ds{font-family:var(--mono);font-size:12px;font-weight:500;text-align:right;color:#155E75}
.ptxt{font-size:12.5px;color:#333B43;line-height:1.55}
.tli{display:grid;grid-template-columns:14px 1fr;gap:10px;padding-bottom:12px}
.td{width:9px;height:9px;border-radius:50%;background:#0E7490;margin-top:4px}
.tev{font-size:12px;font-weight:500;color:#0F1216;text-transform:capitalize}
.tts{font-family:var(--mono);font-size:10px;color:#69727E;margin-top:1px;line-height:1.4}
.acts{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.btnext{font-family:var(--mono);font-size:11px;color:#155E75;border:0.5px solid #9FE1CB;border-radius:4px;padding:7px 12px;text-decoration:none}
.soon{font-family:var(--mono);font-size:10px;color:#9AA2AC}
"""

ICONS = {
    "home": '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 11 12 3l9 8M5 10v10h14V10"/></svg>',
    "bolt": '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2 3 14h7l-1 8 10-12h-7l1-8z"/></svg>',
    "list": '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>',
    "target": '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/></svg>',
    "map": '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 3 3 6v15l6-3 6 3 6-3V3l-6 3-6-3z"/><path d="M9 3v15M15 6v15"/></svg>',
    "chart": '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>',
    "mountain": '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m3 20 6-12 4 7 3-5 5 10z"/></svg>',
    "eye": '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></svg>',
    "ai": '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="8" width="16" height="11" rx="2"/><path d="M12 8V4M9 13h.01M15 13h.01"/></svg>',
    "clock": '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#B91C1C" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
    "inbox": '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#155E75" stroke-width="2"><path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5 5h14l3 7v6a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-6z"/></svg>',
    "search": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#69727E" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>',
}


def nav_item(view, icon, label, active=False, badge=None):
    bdg = f'<span class="bdg">{badge}</span>' if badge else ""
    return (f'<button class="item{" on" if active else ""}" onclick="go(\'{view}\')">'
            f'<span class="ic">{ICONS[icon]}</span>{label}{bdg}</button>')


rail = f"""
<aside class="rail">
  <div class="brand"><div class="mark">L</div><div><div class="bname">Loveo</div><div class="bsub">CONSTRUCCIONES</div></div></div>
  <div class="grp">OPERACIÓN</div>
  {nav_item("inicio","home","Inicio",active=True)}
  {nav_item("senales","bolt","Señales",badge=(len(groups["nuevas"]) or None))}
  {nav_item("listado","list","Listado")}
  {nav_item("radar","target","Radar")}
  {nav_item("mapa","map","Mapa")}
  <div class="grp">INTELIGENCIA</div>
  {nav_item("competitiva","chart","Competitiva")}
  {nav_item("desiertas","mountain","Desiertas")}
  {nav_item("competencia","eye","Competencia")}
  <div class="grp">ASISTENTE</div>
  {nav_item("asistente","ai","Asistente IA")}
  <div class="who"><div class="av">MT</div><div><div class="wn">Martín T.</div><div class="wr">BUSINESS DEV</div></div></div>
</aside>
"""

ICONS_JS = json.dumps({"clock": ICONS["clock"], "inbox": ICONS["inbox"]})

JS_APP = r"""
var ICONS = __ICONS__;
var stack = [{t:'inicio'}];
var TRI = {'Priorizar':['#3B6D11','#EAF3DE','PRIORIZAR'],'Revisar':['#854F0B','#FAEEDA','REVISAR'],'Descartar candidato':['#791F1F','#FCEBEB','DESCARTAR']};
var CRUMBS = {inicio:'INICIO',senales:'SEÑALES',listado:'LISTADO',radar:'RADAR',mapa:'MAPA',competitiva:'INTELIGENCIA',desiertas:'DESIERTAS',competencia:'COMPETENCIA',asistente:'ASISTENTE IA'};
var PHLABEL = {senales:'Señales',listado:'Listado',radar:'Radar',mapa:'Mapa',competitiva:'Inteligencia competitiva',desiertas:'Desiertas',competencia:'Seguimiento de Competencia',asistente:'Asistente IA'};
var MP = 'https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion=';

function esc(s){var d=document.createElement('div');d.textContent=(s==null?'':s);return d.innerHTML;}
function pill(t){if(!t)return '<span style="color:#9AA2AC;font-family:var(--mono);font-size:10px">—</span>';var c=TRI[t]||['#69727E','#F1EFE8',(''+t).toUpperCase()];return '<span class="pill" style="color:'+c[0]+';background:'+c[1]+'">'+c[2]+'</span>';}
function diasTxt(d){if(d==null)return '—';if(d<0)return 'cerrada';if(d===0)return 'HOY';if(d===1)return '1 día';return d+' días';}
function diasChip(d){var red=d<=2;return '<span class="diaschip" style="'+(red?'color:#fff;background:#B91C1C':'color:#854F0B;background:#FAEEDA')+'">'+(d===0?'HOY':(d===1?'1 DÍA':d+' DÍAS'))+'</span>';}

function getGroup(key){
  if(D.groups[key])return D.groups[key];
  var p=key.indexOf(':');var pre=key.slice(0,p),val=key.slice(p+1);var out=[];
  for(var i=0;i<D.order.length;i++){var cod=D.order[i];var l=D.lics[cod];
    if(pre==='reg'&&l.reg===val)out.push(cod);
    else if(pre==='org'&&l.org===val)out.push(cod);}
  return out;
}

function backBtn(){return '<button class="backbtn" data-back="1"><span style="font-size:14px">←</span> Volver</button>';}

function cierranRow(cod){var l=D.lics[cod];var borde=(l.dias<=2)?'#B91C1C':'#F59E0B';
  return '<div class="crow" style="border-left:3px solid '+borde+'" data-ficha="'+esc(cod)+'">'
    +diasChip(l.dias)+'<span class="code">'+esc(l.cod)+'</span>'
    +'<span class="nm">'+esc(l.nom)+'</span><span class="rg">'+esc(l.regc)+'</span>'+pill(l.tri)+'</div>';}

function nuevaRow(cod){var l=D.lics[cod];
  return '<div class="crow" data-ficha="'+esc(cod)+'"><span class="code">'+esc(l.cod)+'</span>'
    +'<span class="nm">'+esc(l.nom)+'</span><span class="rg">'+esc(l.regc)+'</span>'
    +'<span style="font-family:var(--mono);font-size:11px;color:#155E75">'+(l.score!=null?l.score:'—')+'<span style="color:#9AA2AC">/120</span></span>'+pill(l.tri)+'</div>';}

function listRow(cod){var l=D.lics[cod];
  return '<div class="lrow" data-ficha="'+esc(cod)+'"><span class="code">'+esc(l.cod)+'</span>'
    +'<span class="lnom">'+esc(l.nom)+'</span><span class="lreg">'+esc(l.regc)+'</span>'
    +'<span class="lcie">'+diasTxt(l.dias)+'</span><span class="lsc">'+(l.score!=null?l.score:'—')+'</span>'+pill(l.tri)+'</div>';}

function renderInicio(){
  var g=D.groups,m=D.meta;
  var h='<div class="eyebrow">QUÉ HACER HOY</div><div class="h1">Hola, Martín</div>';
  h+='<div class="sec"><span class="ic">'+ICONS.clock+'</span><span class="t" data-list="cierran" data-title="Cierran esta semana">CIERRAN ESTA SEMANA</span></div><div class="col">';
  if(g.cierran.length){for(var i=0;i<Math.min(6,g.cierran.length);i++)h+=cierranRow(g.cierran[i]);}
  else h+='<div style="font-family:var(--mono);font-size:11px;color:#9AA2AC;padding:8px 2px">Nada cierra en los próximos 7 días.</div>';
  h+='</div>';
  h+='<div class="sec"><span class="ic">'+ICONS.inbox+'</span><span class="t" data-list="nuevas" data-title="Nuevas sin revisar">NUEVAS FIT SIN REVISAR · '+g.nuevas.length+'</span></div><div class="col">';
  if(g.nuevas.length){for(var j=0;j<Math.min(6,g.nuevas.length);j++)h+=nuevaRow(g.nuevas[j]);
    if(g.nuevas.length>6)h+='<div style="font-family:var(--mono);font-size:10px;color:#9AA2AC;margin-top:6px;cursor:pointer" data-list="nuevas" data-title="Nuevas sin revisar">+'+(g.nuevas.length-6)+' más →</div>';}
  else h+='<div style="font-family:var(--mono);font-size:11px;color:#9AA2AC;padding:8px 2px">Sin nuevas por revisar.</div>';
  h+='</div>';
  h+='<div class="kpis">'
    +kpi('FIT ESTE AÑO',g.fitAnio.length,'#155E75','fitAnio','Fit este año '+m.year)
    +kpi('NUEVAS · 7D',g.nuevas7d.length,'#B45309','nuevas7d','Nuevas (7 días)')
    +kpi('SIGUIENDO',g.siguiendo.length,'#155E75','siguiendo','En seguimiento')
    +kpi('CIERRAN ≤5D',g.cierran5.length,'#B91C1C','cierran5','Cierran en 5 días')+'</div>';
  // clasificacion
  var maxMes=1;for(var k=0;k<m.monthsShown;k++){var c=getGroup('mes:'+k).length;if(c>maxMes)maxMes=c;}
  h+='<div class="cols2"><div class="panel"><div class="plabel">01 / CLASIFICACIÓN '+m.year+' · POR MES</div><div style="display:flex;align-items:flex-end;gap:6px;height:96px">';
  for(var mm=0;mm<m.monthsShown;mm++){var cv=getGroup('mes:'+mm).length;var hh=cv?Math.round(60*cv/maxMes):2;var col=cv?'#0E7490':'#E7EAEF';
    h+='<div class="bar" data-list="mes:'+mm+'" data-title="'+esc(m.meses[mm])+' '+m.year+'">'+(cv?'<div style="font-family:var(--mono);font-size:10px;color:#155E75;font-weight:500">'+cv+'</div>':'<div style="height:13px"></div>')
      +'<div class="bc" style="width:60%;max-width:26px;height:'+hh+'px;background:'+col+';border-radius:2px 2px 0 0"></div><div style="font-family:var(--mono);font-size:9px;color:#9AA2AC">'+m.mesAb[mm]+'</div></div>';}
  h+='</div></div><div class="panel"><div class="plabel">POR CATEGORÍA</div>';
  var maxCat=1;for(var a=0;a<m.catOrder.length;a++){var cc=getGroup('cat:'+m.catOrder[a]).length;if(cc>maxCat)maxCat=cc;}
  for(var b=0;b<m.catOrder.length;b++){var nm=m.catOrder[b];var v=getGroup('cat:'+nm).length;var w=v?Math.round(100*v/maxCat):0;
    h+='<div class="catrow" data-list="cat:'+esc(nm)+'" data-title="'+esc(nm)+'"><span style="font-size:11px;color:#333B43">'+esc(nm)+'</span><div class="catbar"><div style="height:100%;width:'+w+'%;background:#159A95"></div></div><span style="font-family:var(--mono);font-size:11px;font-weight:500;text-align:right;color:#155E75">'+v+'</span></div>';}
  h+='</div></div>';
  // embudo
  h+='<div class="panel" style="margin-top:13px"><div class="plabel">02 / EMBUDO POR ESTADO</div>';
  var maxE=1;for(var e=0;e<m.embOrder.length;e++){var ec=getGroup('emb:'+m.embOrder[e]).length;if(ec>maxE)maxE=ec;}
  for(var f=0;f<m.embOrder.length;f++){var ph=m.embOrder[f];var ev=getGroup('emb:'+ph).length;var ew=Math.round(100*ev/maxE);
    h+='<div class="fstage" data-list="emb:'+esc(ph)+'" data-title="'+esc(ph)+'"><span class="fl">'+ph.toUpperCase()+'</span><div class="fbar"><div style="height:100%;width:'+ew+'%;background:'+m.embColors[ph]+'"></div></div><span class="fc">'+ev+'</span></div>';}
  h+='</div>';
  return h;
}
function kpi(label,n,color,key,title){return '<div class="kpi" data-list="'+key+'" data-title="'+esc(title)+'"><div class="l">'+label+'</div><div class="n" style="color:'+color+'">'+n+'</div></div>';}

function renderList(key,title){
  var arr=getGroup(key);
  var h='<div>'+backBtn()+'<div class="eyebrow">LISTADO FILTRADO</div><div class="h1">'+esc(title)+'</div><div class="dsub">'+arr.length+(arr.length===1?' licitación':' licitaciones')+'</div>';
  if(!arr.length)return h+'<div class="empty">Sin resultados.</div></div>';
  h+='<div class="tbl"><div class="thead"><span>CÓDIGO</span><span>NOMBRE</span><span>REGIÓN</span><span>CIERRE</span><span style="text-align:right">SCORE</span><span>TRIAGE</span></div>';
  for(var i=0;i<arr.length;i++)h+=listRow(arr[i]);
  return h+'</div></div>';
}

function renderFicha(cod){
  var l=D.lics[cod];if(!l)return backBtn()+'<div class="empty">No encontrada.</div>';
  var h='<div>'+backBtn();
  h+='<div class="fhead"><div style="flex:1;min-width:240px"><div class="code" style="font-size:12px">'+esc(l.cod)+'</div><div class="h1" style="margin-top:4px">'+esc(l.nom)+'</div>'
    +'<div class="badges">'+pill(l.tri)+'<span class="badge">'+esc(l.estadoLbl)+'</span>'+(l.adm?'<span class="badge adm">Admisible</span>':'')+'</div></div>'
    +'<div class="verdict"><div class="vk">SCORE PROV.</div><div class="vv">'+(l.score!=null?l.score:'—')+'<span>/120</span></div>'+(l.reqBases?'<div class="vx">falta cubicación</div>':'')+'</div></div>';
  h+='<div class="card"><div class="ct">DATOS</div><div class="meta">'
    +'<div><div class="mk">Organismo</div><div class="mv lnk" data-org="'+esc(cod)+'">'+esc(l.org||'—')+'</div></div>'
    +'<div><div class="mk">Región</div><div class="mv lnk" data-reg="'+esc(cod)+'">'+esc(l.regc||'—')+'</div></div>'
    +'<div><div class="mk">Monto estimado</div><div class="mv">'+esc(l.monto)+' '+esc(l.moneda)+'</div></div>'
    +'<div><div class="mk">Cierre</div><div class="mv">'+esc(l.cierreFmt||'—')+(l.dias!=null?' · '+diasTxt(l.dias):'')+'</div></div>'
    +'<div><div class="mk">Visita a terreno</div><div class="mv">'+esc(l.visita||'—')+'</div></div>'
    +'<div><div class="mk">Estado MP</div><div class="mv">'+(l.estMp!=null?('código '+l.estMp):'—')+'</div></div>'
    +'<div><div class="mk">Descubierta</div><div class="mv">'+esc(l.desc||'—')+'</div></div></div></div>';
  if(l.dims&&l.dims.length){h+='<div class="card"><div class="ct">SCORE · 6 DIMENSIONES</div>';
    for(var i=0;i<l.dims.length;i++){var d=l.dims[i];var w=(d.score!=null?d.score*10:0);
      h+='<div class="dim" title="'+esc(d.nota)+'"><div class="dl">'+esc(d.n)+(d.ev?'':'<span class="pend">pend.</span>')+'</div><div class="track"><div class="fill'+(d.ev?'':' pend')+'" style="width:'+w+'%"></div></div><div class="ds">'+(d.ev&&d.score!=null?d.score:'—')+'</div></div>';}
    h+='</div>';}
  if(l.admMot)h+='<div class="card"><div class="ct">ADMISIBILIDAD</div><div class="ptxt">'+esc(l.admMot)+'</div></div>';
  if(l.descr)h+='<div class="card"><div class="ct">DESCRIPCIÓN</div><div class="ptxt">'+esc(l.descr)+'</div></div>';
  if(l.eventos&&l.eventos.length){h+='<div class="card"><div class="ct">TRAZABILIDAD</div>';
    for(var j=0;j<l.eventos.length;j++){var ev=l.eventos[j];
      h+='<div class="tli"><span class="td"></span><div><div class="tev">'+esc(ev.tipo)+'</div><div class="tts">'+esc(ev.ts)+(ev.det?' · '+esc(ev.det):'')+'</div></div></div>';}
    h+='</div>';}
  h+='<div class="card"><div class="ct">ACCIONES</div><div class="acts"><a class="btnext" href="'+MP+encodeURIComponent(l.cod)+'" target="_blank">Ver ficha en Mercado Público ↗</a><span class="soon">Aprobar · Descartar · Chat IA · Documentos — próxima entrega</span></div></div>';
  return h+'</div>';
}

function renderPH(v){return '<div class="eyebrow">EN CONSTRUCCIÓN</div><div class="h1">'+esc(PHLABEL[v]||v)+'</div><div class="ph"><b>'+esc(PHLABEL[v]||v)+'</b> — próxima entrega del rediseño.<br>El chasis y el drill-down ya están; esta vista se cablea en los siguientes pasos.</div>';}

var MAG='<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#69727E" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>';
function naLC(s){return (s==null?'':''+s).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'');}
function listRowsHTML(arr){var h='';for(var i=0;i<arr.length;i++)h+=listRow(arr[i]);return h||'<div class="empty">Sin resultados.</div>';}

function renderListado(){
  return '<div class="eyebrow">UNIVERSO COMPLETO · CHILE</div><div class="h1">Listado de licitaciones</div>'
    +'<div class="filters"><div class="fbox"><span class="fic">#</span><input id="f-cod" oninput="filterListado()" placeholder="Filtrar por ID / código MP…"></div>'
    +'<div class="fbox"><span class="fic">'+MAG+'</span><input id="f-kw" oninput="filterListado()" placeholder="Palabra clave (nombre, organismo, región)…"></div></div>'
    +'<div class="tbl"><div class="thead"><span>CÓDIGO</span><span>NOMBRE</span><span>REGIÓN</span><span>CIERRE</span><span style="text-align:right">SCORE</span><span>TRIAGE</span></div>'
    +'<div id="lst-rows">'+listRowsHTML(D.order)+'</div></div>'
    +'<div class="dsub" id="lst-count" style="margin-top:8px">'+D.order.length+' licitaciones</div>';
}
function filterListado(){
  var cod=naLC(document.getElementById('f-cod').value),kw=naLC(document.getElementById('f-kw').value),out=[];
  for(var i=0;i<D.order.length;i++){var c=D.order[i],l=D.lics[c];
    if(cod&&naLC(l.cod).indexOf(cod)<0)continue;
    if(kw&&naLC(l.nom+' '+l.org+' '+l.reg).indexOf(kw)<0)continue;
    out.push(c);}
  document.getElementById('lst-rows').innerHTML=listRowsHTML(out);
  document.getElementById('lst-count').textContent=out.length+(out.length===1?' licitación':' licitaciones');
}
function renderRadar(){
  var arr=D.groups.siguiendo;
  var h='<div class="eyebrow">TU SEGUIMIENTO</div><div class="h1">Radar</div><div class="dsub">'+arr.length+(arr.length===1?' licitación en seguimiento':' licitaciones en seguimiento')+'</div>';
  if(!arr.length)return h+'<div class="empty">Todavía no seguís ninguna licitación.<br>Cuando pases una a revisión o la apruebes, aparece acá.<br><span style="color:#9AA2AC">El alta manual por código MP y el toggle tabla/kanban llegan en el próximo paso.</span></div>';
  h+='<div class="tbl"><div class="thead"><span>CÓDIGO</span><span>NOMBRE</span><span>REGIÓN</span><span>CIERRE</span><span style="text-align:right">SCORE</span><span>TRIAGE</span></div>';
  for(var i=0;i<arr.length;i++)h+=listRow(arr[i]);
  return h+'</div>';
}
function doSearch(v){
  if(!v||!v.trim()){paint();return;}
  var q=naLC(v),out=[];
  for(var i=0;i<D.order.length;i++){var c=D.order[i],l=D.lics[c];
    if(naLC(l.cod+' '+l.nom+' '+l.org+' '+l.reg).indexOf(q)>=0)out.push(c);}
  var h='<div class="eyebrow">BÚSQUEDA</div><div class="h1">"'+esc(v)+'"</div><div class="dsub">'+out.length+(out.length===1?' resultado':' resultados')+'</div>';
  h+= out.length ? ('<div class="tbl"><div class="thead"><span>CÓDIGO</span><span>NOMBRE</span><span>REGIÓN</span><span>CIERRE</span><span style="text-align:right">SCORE</span><span>TRIAGE</span></div>'+listRowsHTML(out)+'</div>') : '<div class="empty">Sin resultados.</div>';
  document.getElementById('app-content').innerHTML=h;
}

function viewHTML(){var s=stack[stack.length-1];
  if(s.t==='inicio')return renderInicio();
  if(s.t==='list')return renderList(s.key,s.title);
  if(s.t==='ficha')return renderFicha(s.cod);
  if(s.t==='listado')return renderListado();
  if(s.t==='radar')return renderRadar();
  return renderPH(s.t);}

function paint(){document.getElementById('app-content').innerHTML=viewHTML();var sc=document.querySelector('.scroll');if(sc)sc.scrollTop=0;}
function nav(s){stack.push(s);paint();}
function back(){if(stack.length>1){stack.pop();paint();}}
function go(v){stack=[{t:v}];paint();
  document.querySelectorAll('.item').forEach(function(b){b.classList.remove('on')});
  var btn=document.querySelector('.item[onclick="go(\''+v+'\')"]');if(btn)btn.classList.add('on');
  document.getElementById('crumb').textContent=CRUMBS[v]||v.toUpperCase();}

document.addEventListener('click',function(e){
  var b=e.target.closest('[data-back]');if(b){back();return;}
  var f=e.target.closest('[data-ficha]');if(f){nav({t:'ficha',cod:f.getAttribute('data-ficha')});return;}
  var li=e.target.closest('[data-list]');if(li){nav({t:'list',key:li.getAttribute('data-list'),title:li.getAttribute('data-title')});return;}
  var rg=e.target.closest('[data-reg]');if(rg){var l=D.lics[rg.getAttribute('data-reg')];if(l.reg)nav({t:'list',key:'reg:'+l.reg,title:'Región: '+l.regc});return;}
  var og=e.target.closest('[data-org]');if(og){var l2=D.lics[og.getAttribute('data-org')];if(l2.org)nav({t:'list',key:'org:'+l2.org,title:l2.org});return;}
});

function fitHeight(){
  var H=840;
  try{ H=(window.parent&&window.parent.innerHeight)?window.parent.innerHeight:(window.innerHeight||840); }catch(e){ H=window.innerHeight||840; }
  try{ var fe=window.frameElement; if(fe){ fe.style.height=H+'px'; var p=fe.parentElement,n=0; while(p&&n<4){ if(p.style)p.style.height=H+'px'; p=p.parentElement; n++; } } }catch(e){}
  var a=document.querySelector('.app'); if(a)a.style.height=H+'px';
}
fitHeight();
window.addEventListener('resize',fitHeight);
try{ window.parent.addEventListener('resize',fitHeight); }catch(e){}

paint();
"""

JS_APP = JS_APP.replace("__ICONS__", ICONS_JS)

html_doc = (
    '<!doctype html><html lang="es"><head><meta charset="utf-8">'
    '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@700;800&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">'
    '<style>' + STYLE + '</style></head><body><div class="app">' + rail +
    '<main class="main"><div class="topbar">'
    '<span class="crumb">LOVEO // <b id="crumb">INICIO</b></span>'
    '<div class="search">' + ICONS["search"] + '<input id="gsearch" oninput="doSearch(this.value)" placeholder="Buscar código, organismo, comuna…"></div>'
    '<span class="live"><span class="dot"></span>' + str(len(groups["nuevas"])) + ' NUEVAS · ' + str(len(groups["nuevas7d"])) + ' EN 7D</span>'
    '</div><div class="scroll"><div id="app-content"></div></div></main></div>'
    '<script>var D=' + json.dumps(DATA, ensure_ascii=False) + ';\n' + JS_APP + '</script></body></html>'
)

components.html(html_doc, height=900, scrolling=False)
