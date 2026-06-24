/* ============================================================================
 * build_deck.js — Generador del Documento de Producto PO/BA de Loveo Licitaciones
 *
 * Por qué existe: la presentación se versiona de forma reproducible. No se edita
 * el .pptx a mano (se pierde historia); se edita ESTE script y se reexporta.
 *
 * DEPENDENCIAS (una sola vez):
 *   cd docs && npm install          # usa el package.json de esta carpeta
 *   # o global:  npm install -g pptxgenjs react-icons react react-dom sharp
 *
 * CORRER:
 *   cd docs && node build_deck.js
 *   # si instalaste global, antes:  export NODE_PATH=$(npm root -g)
 *   # genera Loveo_Licitaciones_PO-BA_<VER>.pptx
 *
 * SUBIR DE VERSIÓN (flujo de change log):
 *   1. Editá VER y FECHA en el bloque "EDITAR ACÁ" de abajo.
 *      - MAJOR (vX.0): cambia visión, alcance o arquitectura.
 *      - MINOR (v1.X): nueva funcionalidad, refinamiento o corrección.
 *   2. AGREGÁ una fila nueva al array `cl` (slide Change Log). NO borres las
 *      anteriores: el change log es append-only.
 *   3. Si hubo una decisión de arquitectura, AGREGÁ una fila al array `adr`.
 *   4. Actualizá las slides que cambiaron (estado de épicas, roadmap, etc.).
 *   5. Reexportá. El nombre del archivo sale solo de VER.
 *   6. Conservá el .pptx anterior; no lo sobrescribas.
 * ========================================================================== */

const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const FA = require("react-icons/fa");

// ---------- Paleta Loveo (WCAG-audited) ----------
const SLATE = "0F172A";   // dominante oscuro
const TEAL  = "0E7490";   // primario soporte
const AMBER = "F59E0B";   // acento
const LIGHT = "F1F5F9";   // claro
const WHITE = "FFFFFF";
const BODY  = "1E293B";   // slate-800 texto
const MUTE  = "64748B";   // slate-500 texto tenue
const TINT  = "F0F9FB";   // tinte de tarjeta
const GREEN = "047857";   // listo
const LINE  = "E2E8F0";   // borde sutil
const TEALD = "155E75";   // teal oscuro

const W = 13.33, H = 7.5;

// ---------- Iconos ----------
async function icon(IconComponent, color = "#FFFFFF", size = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(
    React.createElement(IconComponent, { color, size: String(size) })
  );
  const png = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + png.toString("base64");
}

async function buildIcons() {
  const set = {
    bullseye: FA.FaBullseye, layers: FA.FaLayerGroup, filter: FA.FaFilter,
    chart: FA.FaChartBar, tasks: FA.FaTasks, check: FA.FaCheckCircle,
    server: FA.FaServer, database: FA.FaDatabase, cog: FA.FaCog,
    table: FA.FaTable, road: FA.FaRoad, warn: FA.FaExclamationTriangle,
    doc: FA.FaFileAlt, history: FA.FaHistory, flag: FA.FaFlagCheckered,
    sitemap: FA.FaSitemap,
  };
  const out = {};
  for (const [k, C] of Object.entries(set)) out[k] = await icon(C, "#FFFFFF", 256);
  return out;
}

const shadow = () => ({ type: "outer", color: "000000", blur: 7, offset: 3, angle: 90, opacity: 0.12 });

(async () => {
  const ic = await buildIcons();
  const pres = new pptxgen();
  pres.defineLayout({ name: "WIDE", width: W, height: H });
  pres.layout = "WIDE";
  pres.author = "Atlas — Co-CEO (PO/BA) · Loveo Construcciones SPA";
  pres.title = "Loveo Licitaciones — Documento de Producto PO/BA v1.0";

  // ====================== EDITAR ACÁ AL SUBIR DE VERSIÓN ======================
  const VER = "v1.0";              // MAJOR.MINOR — ver cabecera del archivo
  const FECHA = "15 jun 2026";     // fecha de esta versión
  const OUTFILE = `Loveo_Licitaciones_PO-BA_${VER}.pptx`;  // nombre derivado
  // ===========================================================================

  // ---------- Helpers ----------
  function footer(slide, n) {
    slide.addText([
      { text: "LOVEO LICITACIONES", options: { color: TEAL, bold: true } },
      { text: "   ·   Documento de Producto PO/BA   ·   " + VER + "   ·   Interno", options: { color: MUTE } },
    ], { x: 0.6, y: 7.08, w: 11.5, h: 0.3, fontSize: 8.5, fontFace: "Arial", align: "left", margin: 0 });
    slide.addText(String(n), { x: 12.5, y: 7.08, w: 0.6, h: 0.3, fontSize: 9, color: MUTE, align: "right", fontFace: "Arial", margin: 0 });
  }

  function header(slide, iconData, title, kicker) {
    slide.addShape(pres.shapes.OVAL, { x: 0.6, y: 0.5, w: 0.62, h: 0.62, fill: { color: TEAL }, shadow: shadow() });
    slide.addImage({ data: iconData, x: 0.755, y: 0.655, w: 0.31, h: 0.31 });
    if (kicker) {
      slide.addText(kicker.toUpperCase(), { x: 1.4, y: 0.46, w: 11, h: 0.28, fontSize: 10.5, color: TEAL, bold: true, fontFace: "Arial", charSpacing: 2, margin: 0 });
      slide.addText(title, { x: 1.4, y: 0.72, w: 11.3, h: 0.55, fontSize: 26, color: SLATE, bold: true, fontFace: "Arial", margin: 0 });
    } else {
      slide.addText(title, { x: 1.4, y: 0.55, w: 11.3, h: 0.62, fontSize: 27, color: SLATE, bold: true, fontFace: "Arial", valign: "middle", margin: 0 });
    }
  }

  function card(slide, x, y, w, h, fill = WHITE) {
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { color: LINE, width: 1 }, shadow: shadow() });
  }

  // ============================================================ S1 — Portada
  let s = pres.addSlide();
  s.background = { color: SLATE };
  s.addShape(pres.shapes.OVAL, { x: 10.6, y: -1.6, w: 4.6, h: 4.6, fill: { color: TEALD, transparency: 55 } });
  s.addShape(pres.shapes.OVAL, { x: 11.6, y: 4.6, w: 3.4, h: 3.4, fill: { color: AMBER, transparency: 78 } });
  s.addText("DOCUMENTO DE PRODUCTO  ·  PO / BA", { x: 0.9, y: 1.5, w: 10, h: 0.4, fontSize: 13, color: AMBER, bold: true, charSpacing: 3, fontFace: "Arial", margin: 0 });
  s.addText("Loveo Licitaciones", { x: 0.85, y: 1.95, w: 11, h: 1.0, fontSize: 52, color: WHITE, bold: true, fontFace: "Arial", margin: 0 });
  s.addText("Plataforma de inteligencia de licitaciones de Mercado Público", { x: 0.9, y: 3.05, w: 10.5, h: 0.5, fontSize: 18, color: LIGHT, fontFace: "Arial", margin: 0 });
  s.addText([
    { text: "Descubrir → Filtrar → Descargar → Puntuar → Decidir", options: { color: "CBD5E1", italic: true } },
  ], { x: 0.9, y: 3.55, w: 10, h: 0.4, fontSize: 13, fontFace: "Arial", margin: 0 });

  // meta block
  const meta = [
    ["Versión", VER + "  —  Línea base"],
    ["Fecha", FECHA],
    ["Preparado por", "Atlas — Co-CEO (rol PO / BA)"],
    ["Dirigido a", "VP de Producto → CEO (M. Testa)"],
    ["Clasificación", "Interno · Loveo Construcciones SPA"],
  ];
  let my = 4.55;
  meta.forEach(([k, v]) => {
    s.addText(k.toUpperCase(), { x: 0.9, y: my, w: 2.6, h: 0.3, fontSize: 10, color: TEAL, bold: true, charSpacing: 1, fontFace: "Arial", margin: 0 });
    s.addText(v, { x: 3.5, y: my, w: 8, h: 0.3, fontSize: 11.5, color: WHITE, fontFace: "Arial", margin: 0 });
    my += 0.42;
  });

  // ============================================================ S2 — Propósito & versionado
  s = pres.addSlide(); s.background = { color: WHITE };
  header(s, ic.bullseye, "Propósito del documento y control de versiones", "Cómo leer esto");
  card(s, 0.6, 1.55, 6.0, 5.2);
  s.addText("Para qué sirve", { x: 0.9, y: 1.8, w: 5.4, h: 0.35, fontSize: 15, bold: true, color: TEALD, fontFace: "Arial", margin: 0 });
  s.addText([
    { text: "Un único artefacto vivo que documenta visión, alcance, arquitectura y estado del producto.", options: { bullet: true, breakLine: true } },
    { text: "Lenguaje PO/BA para que el VP de Producto lo presente al CEO sin traducción.", options: { bullet: true, breakLine: true } },
    { text: "Trazabilidad: cada versión apila una fila en el change log; nada se pierde ni se sobrescribe en silencio.", options: { bullet: true, breakLine: true } },
    { text: "Honestidad de estado: marca explícita de lo verificado vs lo pendiente. Sin humo.", options: { bullet: true } },
  ], { x: 0.9, y: 2.25, w: 5.45, h: 4.3, fontSize: 12.5, color: BODY, fontFace: "Arial", paraSpaceAfter: 10, lineSpacingMultiple: 1.05, margin: 0 });

  card(s, 6.85, 1.55, 5.88, 5.2, TINT);
  s.addText("Semántica de versiones", { x: 7.15, y: 1.8, w: 5.3, h: 0.35, fontSize: 15, bold: true, color: TEALD, fontFace: "Arial", margin: 0 });
  s.addText([
    { text: "MAJOR.MINOR", options: { bold: true, color: SLATE, breakLine: true } },
    { text: "MAJOR  ", options: { bold: true, color: AMBER } },
    { text: "→ cambia la visión, el alcance o la arquitectura.", options: { color: BODY, breakLine: true } },
    { text: "MINOR  ", options: { bold: true, color: TEAL } },
    { text: "→ nueva funcionalidad, refinamiento o corrección.", options: { color: BODY, breakLine: true } },
  ], { x: 7.15, y: 2.25, w: 5.3, h: 1.3, fontSize: 12.5, fontFace: "Arial", paraSpaceAfter: 6, margin: 0 });
  s.addText("Reglas de trazabilidad", { x: 7.15, y: 3.65, w: 5.3, h: 0.32, fontSize: 13, bold: true, color: SLATE, fontFace: "Arial", margin: 0 });
  s.addText([
    { text: "El nombre del archivo lleva la versión: Loveo_Licitaciones_PO-BA_v1.0.pptx", options: { bullet: true, breakLine: true } },
    { text: "Cada versión nueva = una entrada fechada en la slide de Change Log.", options: { bullet: true, breakLine: true } },
    { text: "La versión anterior se conserva; el deck nunca se edita en su lugar perdiendo historia.", options: { bullet: true } },
  ], { x: 7.15, y: 4.05, w: 5.3, h: 2.5, fontSize: 12, color: BODY, fontFace: "Arial", paraSpaceAfter: 9, margin: 0 });
  footer(s, 2);

  // ============================================================ S3 — Resumen ejecutivo
  s = pres.addSlide(); s.background = { color: WHITE };
  header(s, ic.chart, "Resumen ejecutivo", "Dónde estamos");
  const stats = [
    ["1.186", "licitaciones/día hábil leídas por la API oficial", TEAL],
    ["11", "candidatos tras el filtro de keywords afinado", AMBER],
    ["2 / 8", "capas del pipeline ya operativas (descubrir + estado)", TEALD],
    ["$0", "costo del descubrimiento: API pública y gratuita", GREEN],
  ];
  let sx = 0.6;
  stats.forEach(([big, lab, col]) => {
    card(s, sx, 1.55, 2.93, 1.7);
    s.addText(big, { x: sx, y: 1.7, w: 2.93, h: 0.85, fontSize: 40, bold: true, color: col, align: "center", fontFace: "Arial", margin: 0 });
    s.addText(lab, { x: sx + 0.18, y: 2.55, w: 2.57, h: 0.62, fontSize: 10, color: MUTE, align: "center", fontFace: "Arial", margin: 0 });
    sx += 3.06;
  });
  card(s, 0.6, 3.5, 12.13, 3.25, TINT);
  s.addText("La tesis, en tres frases", { x: 0.95, y: 3.72, w: 11, h: 0.35, fontSize: 15, bold: true, color: TEALD, fontFace: "Arial", margin: 0 });
  s.addText([
    { text: "Las herramientas existentes (Vendify, LicitaLAB, Smartoffer) descubren y emparejan licitaciones de forma genérica; ninguna aplica la economía real de Loveo a la decisión GO/NO-GO.", options: { bullet: true, breakLine: true } },
    { text: "El diferencial defendible no es el monitoreo —que es commodity sobre una API gratuita— sino el scoring Atlas (margen ≥25%, sobrecosto 30%, multiplicador logístico ×3 a >300 km, ventaja Puerto Montt) más el loop de feedback y la trazabilidad de punta a punta.", options: { bullet: true, breakLine: true } },
    { text: "Decisión de construcción: poseer el pipeline completo sobre la API oficial (barato y estable) y concentrar el esfuerzo en la capa de inteligencia. Hoy: Capa A verificada en vivo; Capa B (descarga) en calibración.", options: { bullet: true } },
  ], { x: 0.95, y: 4.15, w: 11.45, h: 2.45, fontSize: 12, color: BODY, fontFace: "Arial", paraSpaceAfter: 9, lineSpacingMultiple: 1.03, margin: 0 });
  footer(s, 3);

  // ============================================================ S4 — Visión y 3 horizontes
  s = pres.addSlide(); s.background = { color: WHITE };
  header(s, ic.layers, "Visión de producto: tres horizontes", "Hacia dónde");
  const hz = [
    ["H1", "Herramienta interna", "Pipeline de licitaciones + CoMS como sistema operativo de Loveo. Test del producto sobre nosotros mismos.", "Ahora → post-gate", TEAL],
    ["H2", "Producto SaaS", "Plataforma multi-empresa para cualquier proveedor del Estado: prospección + costeo + gestión.", "6–12 meses", TEALD],
    ["H3", "Fintech", "Préstamos de capital de trabajo con underwriting basado en la data de H2.", "18–24 meses", "92400E"],
  ];
  let hx = 0.6;
  hz.forEach(([tag, t, d, when, col]) => {
    card(s, hx, 1.6, 3.9, 3.55);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: hx + 0.3, y: 1.9, w: 1.0, h: 0.6, rectRadius: 0.06, fill: { color: col } });
    s.addText(tag, { x: hx + 0.3, y: 1.9, w: 1.0, h: 0.6, fontSize: 22, bold: true, color: WHITE, align: "center", valign: "middle", fontFace: "Arial", margin: 0 });
    s.addText(t, { x: hx + 0.3, y: 2.68, w: 3.3, h: 0.4, fontSize: 16, bold: true, color: SLATE, fontFace: "Arial", margin: 0 });
    s.addText(d, { x: hx + 0.3, y: 3.12, w: 3.35, h: 1.45, fontSize: 11.5, color: BODY, fontFace: "Arial", lineSpacingMultiple: 1.05, margin: 0 });
    s.addText(when.toUpperCase(), { x: hx + 0.3, y: 4.6, w: 3.3, h: 0.35, fontSize: 10, bold: true, color: col, charSpacing: 1, fontFace: "Arial", margin: 0 });
    hx += 4.07;
  });
  card(s, 0.6, 5.45, 12.13, 1.3, SLATE);
  s.addText([
    { text: "Regla de oro entre horizontes (anti-Katerra):  ", options: { bold: true, color: AMBER } },
    { text: "cada horizonte se valida antes de financiar el siguiente. No se escala la infraestructura más rápido que la demanda confirmada.", options: { color: WHITE } },
  ], { x: 1.0, y: 5.45, w: 11.3, h: 1.3, fontSize: 13.5, fontFace: "Arial", valign: "middle", lineSpacingMultiple: 1.05, margin: 0 });
  footer(s, 4);

  // ============================================================ S5 — Problema / diferenciación
  s = pres.addSlide(); s.background = { color: WHITE };
  header(s, ic.filter, "El problema y el diferencial de Loveo", "Por qué construir");
  // izquierda: el embudo
  s.addText("El embudo del proveedor del Estado", { x: 0.6, y: 1.65, w: 6, h: 0.35, fontSize: 14, bold: true, color: TEALD, fontFace: "Arial", margin: 0 });
  const fun = [
    ["1 · Prospección", "detectar licitaciones que calzan", "cubierto por SaaS genérico"],
    ["2 · Evaluación", "decidir GO/NO-GO, puntuar", "parcial — genérico, sin tu economía"],
    ["3 · Preparación", "armar anexos, precio", "cubierto por SaaS genérico"],
    ["4 · Adjudicación", "ganás o no", "fin de la cobertura existente"],
  ];
  let fy = 2.1;
  fun.forEach(([a, b, c], i) => {
    card(s, 0.6, fy, 6.05, 0.74, i < 2 ? TINT : WHITE);
    s.addText(a, { x: 0.8, y: fy + 0.08, w: 2.1, h: 0.58, fontSize: 12.5, bold: true, color: SLATE, valign: "middle", fontFace: "Arial", margin: 0 });
    s.addText([{ text: b, options: { color: BODY, breakLine: true } }, { text: c, options: { color: MUTE, italic: true, fontSize: 9.5 } }],
      { x: 2.95, y: fy + 0.06, w: 3.6, h: 0.62, fontSize: 11, valign: "middle", fontFace: "Arial", margin: 0 });
    fy += 0.82;
  });
  // derecha: el diferencial
  card(s, 6.95, 2.1, 5.78, 3.78, SLATE);
  s.addText("Lo que nadie hace, y es nuestro foso", { x: 7.25, y: 2.3, w: 5.2, h: 0.4, fontSize: 15, bold: true, color: AMBER, fontFace: "Arial", margin: 0 });
  s.addText([
    { text: "Scoring Atlas con la economía real de Loveo", options: { bullet: { code: "2713" }, color: WHITE, bold: true, breakLine: true } },
    { text: "margen ≥25%, sobrecosto 30%, ×3 logístico >300 km, ventaja Puerto Montt", options: { color: "CBD5E1", fontSize: 10.5, breakLine: true, indentLevel: 1 } },
    { text: "Loop de feedback humano sobre el score", options: { bullet: { code: "2713" }, color: WHITE, bold: true, breakLine: true } },
    { text: "vos corregís; el filtro y el criterio mejoran solos", options: { color: "CBD5E1", fontSize: 10.5, breakLine: true, indentLevel: 1 } },
    { text: "Trazabilidad de punta a punta", options: { bullet: { code: "2713" }, color: WHITE, bold: true, breakLine: true } },
    { text: "de descubierta a ganada/perdida, auditable", options: { color: "CBD5E1", fontSize: 10.5, indentLevel: 1 } },
  ], { x: 7.25, y: 2.78, w: 5.2, h: 3.0, fontSize: 12.5, fontFace: "Arial", paraSpaceAfter: 5, margin: 0 });
  s.addText([
    { text: "Veredicto:  ", options: { bold: true, color: SLATE } },
    { text: "el monitoreo es commodity; la inteligencia económica es el producto.", options: { color: BODY, italic: true } },
  ], { x: 0.6, y: 6.05, w: 12.1, h: 0.5, fontSize: 12.5, fontFace: "Arial", margin: 0 });
  footer(s, 5);

  // ============================================================ S6 — Mercado
  s = pres.addSlide(); s.background = { color: WHITE };
  header(s, ic.chart, "Oportunidad de mercado", "El tamaño del problema");
  s.addChart(pres.charts.BAR, [
    { name: "Adjudicadas", labels: ["RM", "Biobío", "Araucanía", "Valparaíso", "Los Lagos"], values: [759, 331, 306, 305, 216] },
  ], {
    x: 0.6, y: 1.7, w: 6.5, h: 4.4, barDir: "col",
    chartColors: [TEAL], chartArea: { fill: { color: WHITE } },
    catAxisLabelColor: MUTE, valAxisLabelColor: MUTE, catAxisLabelFontFace: "Arial", valAxisLabelFontFace: "Arial",
    catAxisLabelFontSize: 11, valAxisLabelFontSize: 10,
    valGridLine: { color: LINE, size: 0.5 }, catGridLine: { style: "none" },
    showValue: true, dataLabelPosition: "outEnd", dataLabelColor: SLATE, dataLabelFontFace: "Arial", dataLabelFontSize: 10,
    showLegend: false, showTitle: true, title: 'Licitaciones por región — categoría "Unidades para contenedores"',
    titleColor: SLATE, titleFontFace: "Arial", titleFontSize: 12,
  });
  const mk = [
    ["US$ 111 B", "mercado modular global 2025 · CAGR 8,2%", "Grand View Research"],
    ["US$ 32,1 B", "construcción Chile 2024 · CAGR 5%", "Informes de Expertos"],
    ["2.885", "licitaciones de contenedores · 1.894 adjudicadas (66%)", "todolicitaciones.cl, mar-2026"],
    ["25%", "de esas licitaciones quedan desiertas → oportunidad", "ChileCompra"],
  ];
  let mky = 1.7;
  mk.forEach(([big, lab, src]) => {
    card(s, 7.4, mky, 5.33, 1.2);
    s.addText(big, { x: 7.65, y: mky + 0.12, w: 2.3, h: 0.9, fontSize: 26, bold: true, color: TEALD, valign: "middle", fontFace: "Arial", margin: 0 });
    s.addText([{ text: lab, options: { color: BODY, breakLine: true, fontSize: 11 } }, { text: src, options: { color: MUTE, italic: true, fontSize: 9 } }],
      { x: 9.95, y: mky + 0.1, w: 2.6, h: 1.0, valign: "middle", fontFace: "Arial", margin: 0 });
    mky += 1.27;
  });
  s.addText("Fuentes: Grand View Research 2025; Informes de Expertos 2025; McKinsey 2025; ChileCompra; todolicitaciones.cl (mar-2026). Cifras de referencia, no un SAM cerrado.",
    { x: 0.6, y: 6.55, w: 12.1, h: 0.4, fontSize: 8.5, color: MUTE, italic: true, fontFace: "Arial", margin: 0 });
  footer(s, 6);

  // ============================================================ S7 — Alcance funcional (épicas)
  s = pres.addSlide(); s.background = { color: WHITE };
  header(s, ic.tasks, "Alcance funcional: el pipeline como 8 épicas", "Qué hace el producto");
  const rowsE = [
    ["#", "Épica", "Qué hace", "Costo", "Estado"],
    ["1", "Descubrir", "API oficial ChileCompra, listado diario", "Bajo", "Listo"],
    ["2", "Filtrar", "Keywords límite de palabra + exclusiones", "Bajo", "Listo"],
    ["3", "Admisibilidad", "Filtro eliminatorio Loveo (regla dura)", "Bajo", "Siguiente"],
    ["4", "Descargar", "Navegador headless: bases + anexos", "Alto", "Calibrando"],
    ["5", "Leer + puntuar", "Claude API lee docs, aplica scoring Atlas", "Medio", "Capa C"],
    ["6", "Presentar", "Tablero: resumen, score, acceso a docs", "Medio", "Pendiente"],
    ["7", "Feedback", "Validás/corregís el score", "Bajo", "Pendiente"],
    ["8", "Estado", "Trazabilidad doble eje + eventos", "Bajo", "Listo"],
  ];
  const stColor = { "Listo": GREEN, "Calibrando": AMBER, "Siguiente": TEAL, "Capa C": MUTE, "Pendiente": MUTE };
  const tblE = rowsE.map((r, ri) => r.map((cell, ci) => {
    if (ri === 0) return { text: cell, options: { fill: { color: SLATE }, color: WHITE, bold: true, fontSize: 12, align: ci === 0 ? "center" : "left", valign: "middle" } };
    const base = { fontSize: 11.5, color: BODY, valign: "middle", fill: { color: ri % 2 ? WHITE : LIGHT } };
    if (ci === 0) return { text: cell, options: { ...base, align: "center", bold: true, color: TEAL } };
    if (ci === 4) return { text: cell, options: { ...base, bold: true, color: stColor[cell] || BODY } };
    if (ci === 1) return { text: cell, options: { ...base, bold: true, color: SLATE } };
    return { text: cell, options: base };
  }));
  s.addTable(tblE, { x: 0.6, y: 1.6, w: 12.13, colW: [0.7, 2.2, 6.13, 1.4, 1.7], rowH: 0.52, border: { type: "solid", pt: 0.5, color: LINE }, fontFace: "Arial", valign: "middle" });
  footer(s, 7);

  // ============================================================ S8 — Estado verificado (probe)
  s = pres.addSlide(); s.background = { color: WHITE };
  header(s, ic.check, "Estado verificado en vivo (sin humo)", "Probe 14-jun-2026");
  const vf = [
    ["check", GREEN, "API de descubrimiento operativa", "api.mercadopublico.cl → 200. 1.186 licitaciones del día hábil, ~50 campos por detalle, incluido el bloque Adjudicación con el competidor."],
    ["check", GREEN, "Filtro afinado", "1.186 → 11 candidatos reales. Apareció solo el container de Cunco que ya estaba en pipeline."],
    ["warn", AMBER, "La API NO entrega los archivos", "Confirmado con data 2026: cero adjuntos en el detalle. Los anexos viven solo en la ficha → obligan navegador (Capa B)."],
    ["warn", AMBER, "El portal bloquea IP de datacenter", "www.mercadopublico.cl → 403 desde servidor. La descarga corre local, sobre IP residencial CL. Es el modelo local-first, no un bug."],
  ];
  let vy = 1.65, vxs = [0.6, 6.75];
  vf.forEach((f, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const X = vxs[col], Y = 1.65 + row * 2.55;
    card(s, X, Y, 5.98, 2.35);
    s.addShape(pres.shapes.OVAL, { x: X + 0.28, y: Y + 0.28, w: 0.6, h: 0.6, fill: { color: f[1] } });
    s.addImage({ data: ic[f[0]], x: X + 0.42, y: Y + 0.42, w: 0.32, h: 0.32 });
    s.addText(f[2], { x: X + 1.05, y: Y + 0.28, w: 4.7, h: 0.6, fontSize: 14.5, bold: true, color: SLATE, valign: "middle", fontFace: "Arial", margin: 0 });
    s.addText(f[3], { x: X + 0.32, y: Y + 1.0, w: 5.4, h: 1.25, fontSize: 11.5, color: BODY, fontFace: "Arial", lineSpacingMultiple: 1.05, margin: 0 });
  });
  footer(s, 8);

  // ============================================================ S9 — Arquitectura
  s = pres.addSlide(); s.background = { color: WHITE };
  header(s, ic.server, "Arquitectura técnica", "Cómo está construido");
  // fila de bloques de flujo
  const flow = [
    ["API ChileCompra", "fuente oficial, gratis", TEAL],
    ["Capa A · Descubrir/Filtrar", "server o local", TEALD],
    ["SQLite + ./storage", "fuente de verdad local-first", SLATE],
    ["Capa C · Scoring", "Claude API lee ./storage", TEALD],
  ];
  let fx = 0.6;
  flow.forEach((b, i) => {
    card(s, fx, 1.75, 2.72, 1.5, i === 2 ? SLATE : WHITE);
    const tc = i === 2 ? WHITE : SLATE, sc = i === 2 ? "CBD5E1" : MUTE;
    s.addText(b[0], { x: fx + 0.15, y: 1.92, w: 2.42, h: 0.7, fontSize: 12.5, bold: true, color: tc, align: "center", valign: "middle", fontFace: "Arial", margin: 0 });
    s.addText(b[1], { x: fx + 0.15, y: 2.62, w: 2.42, h: 0.5, fontSize: 9.5, color: sc, align: "center", fontFace: "Arial", margin: 0 });
    if (i < 3) s.addText("→", { x: fx + 2.72, y: 1.75, w: 0.35, h: 1.5, fontSize: 22, color: AMBER, bold: true, align: "center", valign: "middle", fontFace: "Arial", margin: 0 });
    fx += 3.07;
  });
  // capa B destacada
  card(s, 0.6, 3.55, 8.0, 1.55, TINT);
  s.addShape(pres.shapes.OVAL, { x: 0.9, y: 3.95, w: 0.7, h: 0.7, fill: { color: AMBER } });
  s.addImage({ data: ic.cog, x: 1.07, y: 4.12, w: 0.36, h: 0.36 });
  s.addText([
    { text: "Capa B · Descarga de adjuntos — corre SIEMPRE local", options: { bold: true, color: SLATE, breakLine: true, fontSize: 14 } },
    { text: "Navegador headless (Playwright) sobre IP residencial CL (notebook / oficina Puerto Montt / proxy residencial). Guarda en ./storage/<codigo>/ con hash sha256 y dedup.", options: { color: BODY, fontSize: 11 } },
  ], { x: 1.8, y: 3.7, w: 6.6, h: 1.25, valign: "middle", fontFace: "Arial", lineSpacingMultiple: 1.03, margin: 0 });
  // sync card
  card(s, 8.85, 3.55, 3.88, 1.55, WHITE);
  s.addText([
    { text: "Sync a la nube", options: { bold: true, color: TEALD, breakLine: true, fontSize: 13 } },
    { text: "Supabase con el MISMO esquema, post-gate. Enchufar el online no obliga a reescribir nada.", options: { color: BODY, fontSize: 11 } },
  ], { x: 9.1, y: 3.72, w: 3.4, h: 1.25, valign: "middle", fontFace: "Arial", lineSpacingMultiple: 1.03, margin: 0 });
  s.addText([
    { text: '"Online y offline":  ', options: { bold: true, color: SLATE } },
    { text: "lo descargado se revisa y se baja sin internet; la nube solo agrega multi-usuario.", options: { color: BODY, italic: true } },
  ], { x: 0.6, y: 5.45, w: 12.1, h: 0.9, fontSize: 12.5, fontFace: "Arial", valign: "middle", margin: 0 });
  footer(s, 9);

  // ============================================================ S10 — Modelo de datos + estados
  s = pres.addSlide(); s.background = { color: WHITE };
  header(s, ic.database, "Modelo de datos y máquina de estados", "Artefacto BA");
  s.addText("Entidades (SQLite)", { x: 0.6, y: 1.6, w: 5.5, h: 0.35, fontSize: 14, bold: true, color: TEALD, fontFace: "Arial", margin: 0 });
  const ent = [
    ["licitaciones", "codigo (PK), metadata, doble eje de estado, score, json_detalle crudo"],
    ["documentos", "archivos descargados, ruta local, sha256, dedup por (codigo, hash)"],
    ["eventos", "log de auditoría: descubierta, cambio_estado, descarga, score, feedback"],
  ];
  let ey = 2.05;
  ent.forEach(([n, d]) => {
    card(s, 0.6, ey, 6.05, 1.05);
    s.addText(n, { x: 0.85, y: ey + 0.12, w: 5.6, h: 0.35, fontSize: 13.5, bold: true, color: SLATE, fontFace: "Courier New", margin: 0 });
    s.addText(d, { x: 0.85, y: ey + 0.5, w: 5.6, h: 0.5, fontSize: 10.5, color: BODY, fontFace: "Arial", lineSpacingMultiple: 1.0, margin: 0 });
    ey += 1.15;
  });
  // máquina de estados doble eje
  s.addText("Máquina de estados — doble eje", { x: 6.95, y: 1.6, w: 5.8, h: 0.35, fontSize: 14, bold: true, color: TEALD, fontFace: "Arial", margin: 0 });
  function stateBox(x, y, w, t, fill, tc) {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h: 0.5, rectRadius: 0.06, fill: { color: fill }, line: { color: LINE, width: 1 } });
    s.addText(t, { x, y, w, h: 0.5, fontSize: 10.5, bold: true, color: tc, align: "center", valign: "middle", fontFace: "Arial", margin: 0 });
  }
  function arrow(x, y, w) { s.addText("→", { x, y, w, h: 0.5, fontSize: 16, color: AMBER, bold: true, align: "center", valign: "middle", margin: 0 }); }
  s.addText("Eje 1 — Revisión interna", { x: 6.95, y: 2.1, w: 5.8, h: 0.3, fontSize: 11, bold: true, color: MUTE, fontFace: "Arial", margin: 0 });
  stateBox(6.95, 2.45, 1.35, "nueva", LIGHT, SLATE); arrow(8.3, 2.45, 0.35);
  stateBox(8.65, 2.45, 1.55, "en_revisión", LIGHT, SLATE); arrow(10.2, 2.45, 0.35);
  stateBox(10.55, 2.45, 1.35, "aprobada", TEAL, WHITE);
  stateBox(10.55, 3.05, 1.35, "descartada", "FEE2E2", "991B1B");
  s.addText("Eje 2 — Resultado (si aprobada)", { x: 6.95, y: 3.75, w: 5.8, h: 0.3, fontSize: 11, bold: true, color: MUTE, fontFace: "Arial", margin: 0 });
  stateBox(6.95, 4.1, 1.45, "pendiente", LIGHT, SLATE); arrow(8.4, 4.1, 0.3);
  stateBox(8.7, 4.1, 1.5, "presentada", LIGHT, SLATE); arrow(10.2, 4.1, 0.3);
  stateBox(10.5, 4.1, 1.4, "ganada", GREEN, WHITE);
  stateBox(8.7, 4.7, 1.5, "perdida", "FEE2E2", "991B1B");
  stateBox(10.5, 4.7, 1.4, "desierta", LIGHT, MUTE);
  card(s, 6.95, 5.5, 5.78, 0.95, TINT);
  s.addText([
    { text: "Por qué dos ejes:  ", options: { bold: true, color: SLATE } },
    { text: "el estado de revisión (lo que decidimos) es independiente del resultado (lo que pasó). Mezclarlos rompe la trazabilidad.", options: { color: BODY } },
  ], { x: 7.2, y: 5.5, w: 5.3, h: 0.95, fontSize: 10.5, valign: "middle", fontFace: "Arial", lineSpacingMultiple: 1.0, margin: 0 });
  footer(s, 10);

  // ============================================================ S11 — Requisitos no funcionales
  s = pres.addSlide(); s.background = { color: WHITE };
  header(s, ic.cog, "Requisitos no funcionales", "Artefacto BA");
  const nfr = [
    ["Privacidad", "Ticket de API y calibración de keywords/umbrales en config_local.py (gitignored). Es ventaja competitiva: nunca al repo."],
    ["Resiliencia", "Backoff ante rate-limit (429). El ticket de pruebas se satura; ticket propio + embudo keyword-first lo resuelve."],
    ["Topología", "La descarga exige IP residencial CL (el portal da 403 a datacenter). Runner local; proxy residencial si se nubea."],
    ["Integridad", "Cada documento se hashea (sha256) y se deduplica por (codigo, hash). El json_detalle crudo se guarda para auditoría."],
    ["Costo", "Stack objetivo ~$95.000 CLP/mes ≈ 0,5% de la estructura fija de Puerto Montt ($17,8M). Ruido frente a la operación."],
    ["Auditabilidad", "Tabla eventos registra cada cambio con timestamp. De descubierta a ganada/perdida, todo queda."],
  ];
  let nx = 0.6, ny = 1.65;
  nfr.forEach((f, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const X = 0.6 + col * 6.13, Y = 1.65 + row * 1.62;
    card(s, X, Y, 5.98, 1.45);
    s.addText(f[0], { x: X + 0.25, y: Y + 0.16, w: 5.5, h: 0.35, fontSize: 14, bold: true, color: TEALD, fontFace: "Arial", margin: 0 });
    s.addText(f[1], { x: X + 0.25, y: Y + 0.56, w: 5.5, h: 0.82, fontSize: 11, color: BODY, fontFace: "Arial", lineSpacingMultiple: 1.03, margin: 0 });
  });
  footer(s, 11);

  // ============================================================ S12 — Matriz de trazabilidad
  s = pres.addSlide(); s.background = { color: WHITE };
  header(s, ic.table, "Matriz de trazabilidad de requisitos", "Artefacto BA");
  const rt = [
    ["ID", "Requisito", "Épica", "Implementación", "Estado"],
    ["RF-01", "Descubrir licitaciones diarias", "1", "discover.py · API", "Listo"],
    ["RF-02", "Filtrar sin falsos positivos", "2", "matchea() · límite palabra", "Listo*"],
    ["RF-03", "Descargar los adjuntos", "4", "download.py · Playwright", "Calibrando"],
    ["RF-04", "Acceso del usuario a los documentos", "6", "tablero + ./storage", "Pendiente"],
    ["RF-05", "Scoring Atlas con feedback", "5,7", "Capa C · Claude API", "Pendiente"],
    ["RNF-01", "Trazabilidad de estado", "8", "tabla eventos · doble eje", "Listo"],
    ["RNF-02", "Privacidad de credenciales", "—", "config_local + .gitignore", "Listo"],
  ];
  const tt = rt.map((r, ri) => r.map((cell, ci) => {
    if (ri === 0) return { text: cell, options: { fill: { color: SLATE }, color: WHITE, bold: true, fontSize: 12, valign: "middle", align: ci === 2 ? "center" : "left" } };
    const base = { fontSize: 11.5, color: BODY, valign: "middle", fill: { color: ri % 2 ? WHITE : LIGHT } };
    if (ci === 0) return { text: cell, options: { ...base, bold: true, color: TEAL, fontFace: "Courier New" } };
    if (ci === 2) return { text: cell, options: { ...base, align: "center" } };
    if (ci === 4) {
      const c = cell.startsWith("Listo") ? GREEN : cell === "Calibrando" ? AMBER : MUTE;
      return { text: cell, options: { ...base, bold: true, color: c } };
    }
    return { text: cell, options: base };
  }));
  s.addTable(tt, { x: 0.6, y: 1.65, w: 12.13, colW: [1.2, 4.13, 0.9, 3.9, 2.0], rowH: 0.56, border: { type: "solid", pt: 0.5, color: LINE }, fontFace: "Arial", valign: "middle" });
  s.addText("* RF-02 operativo; queda afinamiento de exclusiones vía loop de feedback (p. ej. plurales).",
    { x: 0.6, y: 6.5, w: 12, h: 0.3, fontSize: 9.5, color: MUTE, italic: true, fontFace: "Arial", margin: 0 });
  footer(s, 12);

  // ============================================================ S13 — Roadmap
  s = pres.addSlide(); s.background = { color: WHITE };
  header(s, ic.road, "Roadmap del producto", "En qué orden");
  const rm = [
    ["AHORA · jun-26", "Capa A verificada. Calibrar Capa B (descarga) en local.", TEAL, "En curso"],
    ["GATE · 1-jul-26", "≥2 licitaciones sur confirmadas. NEGOCIO, no producto: la calle no se reemplaza con código.", AMBER, "Hito"],
    ["POST-GATE · ago-26+", "Capa C (scoring Atlas) + admisibilidad + tablero con acceso a documentos.", TEALD, "Planificado"],
    ["Q4-26", "Tablero multi-usuario: Sheet interino → Streamlit + Supabase. Sync online.", SLATE, "Planificado"],
    ["2027+", "H2 SaaS multi-empresa — solo si H1 queda validado. Anti-Katerra.", "92400E", "Condicional"],
  ];
  let ry = 1.7;
  rm.forEach(([t, d, col, tag]) => {
    s.addShape(pres.shapes.OVAL, { x: 0.7, y: ry + 0.28, w: 0.26, h: 0.26, fill: { color: col } });
    card(s, 1.2, ry, 11.53, 0.92);
    s.addText(t, { x: 1.45, y: ry, w: 3.0, h: 0.92, fontSize: 13, bold: true, color: col, valign: "middle", fontFace: "Arial", margin: 0 });
    s.addText(d, { x: 4.5, y: ry, w: 6.4, h: 0.92, fontSize: 11.5, color: BODY, valign: "middle", fontFace: "Arial", lineSpacingMultiple: 1.02, margin: 0 });
    s.addText(tag.toUpperCase(), { x: 11.0, y: ry, w: 1.55, h: 0.92, fontSize: 9.5, bold: true, color: col, align: "right", valign: "middle", charSpacing: 1, fontFace: "Arial", margin: 0 });
    ry += 1.04;
  });
  footer(s, 13);

  // ============================================================ S14 — Riesgos
  s = pres.addSlide(); s.background = { color: WHITE };
  header(s, ic.warn, "Riesgos y mitigaciones", "Lo que puede salir mal");
  const rk = [
    ["Riesgo", "Prob.", "Mitigación", "Estado"],
    ["Sobre-ingeniería antes del gate (Katerra interno)", "Media", "Solo Capa A/B ahora; el gate es la prioridad real", "Controlado"],
    ["El portal cambia y rompe los selectores", "Media", "Calibración versionada + smoke test que avisa", "Plan"],
    ["Rate-limit de la API bloquea la corrida", "Media", "Ticket propio + backoff + embudo keyword-first", "Mitigado"],
    ["Dependencia de IP residencial para descargar", "Media", "Runner local; proxy residencial CL si se nubea", "Aceptado"],
    ["Falsos positivos del filtro de keywords", "Media", "Límite de palabra + exclusiones + loop feedback", "En curso"],
    ["Fuga de credenciales/calibración al repo", "Baja", ".env y config_local en .gitignore; verificar git", "Mitigado"],
  ];
  const tr = rk.map((r, ri) => r.map((cell, ci) => {
    if (ri === 0) return { text: cell, options: { fill: { color: SLATE }, color: WHITE, bold: true, fontSize: 11.5, valign: "middle", align: ci === 1 || ci === 3 ? "center" : "left" } };
    const base = { fontSize: 11, color: BODY, valign: "middle", fill: { color: ri % 2 ? WHITE : LIGHT } };
    if (ci === 0) return { text: cell, options: { ...base, bold: true, color: SLATE } };
    if (ci === 1) return { text: cell, options: { ...base, align: "center", color: MUTE } };
    if (ci === 3) {
      const c = (cell === "Mitigado" || cell === "Controlado") ? GREEN : cell === "En curso" ? AMBER : MUTE;
      return { text: cell, options: { ...base, align: "center", bold: true, color: c } };
    }
    return { text: cell, options: base };
  }));
  s.addTable(tr, { x: 0.6, y: 1.65, w: 12.13, colW: [4.7, 1.1, 4.63, 1.7], rowH: 0.6, border: { type: "solid", pt: 0.5, color: LINE }, fontFace: "Arial", valign: "middle" });
  footer(s, 14);

  // ============================================================ S15 — ADR log
  s = pres.addSlide(); s.background = { color: WHITE };
  header(s, ic.doc, "Registro de decisiones de arquitectura (ADR)", "Por qué, no solo qué");
  const adr = [
    ["ADR", "Decisión", "Por qué"],
    ["01", "API oficial de ChileCompra, no scraping", "La página de búsqueda es JS frágil; la API es estable y gratis"],
    ["02", "Adjuntos vía navegador, no API", "Verificado: el detalle no trae archivos (0 adjuntos)"],
    ["03", "Local-first SQLite + ./storage", "Portal da 403 a datacenter + requisito offline"],
    ["04", "Python para el motor", "Pipeline de datos + PDF + LLM en un solo stack"],
    ["05", "Calibración privada (config_local)", "Keywords y umbrales son ventaja competitiva"],
    ["06", "Doble eje de estado", "Separar revisión (decisión) de resultado (hecho)"],
    ["07", "No usar LicitaLAB como motor", "Su scoring es genérico; el Atlas es el diferencial"],
  ];
  const ta = adr.map((r, ri) => r.map((cell, ci) => {
    if (ri === 0) return { text: cell, options: { fill: { color: TEALD }, color: WHITE, bold: true, fontSize: 12, valign: "middle", align: ci === 0 ? "center" : "left" } };
    const base = { fontSize: 11, color: BODY, valign: "middle", fill: { color: ri % 2 ? WHITE : LIGHT } };
    if (ci === 0) return { text: cell, options: { ...base, align: "center", bold: true, color: TEAL, fontFace: "Courier New" } };
    if (ci === 1) return { text: cell, options: { ...base, bold: true, color: SLATE } };
    return { text: cell, options: base };
  }));
  s.addTable(ta, { x: 0.6, y: 1.65, w: 12.13, colW: [0.9, 4.6, 6.63], rowH: 0.57, border: { type: "solid", pt: 0.5, color: LINE }, fontFace: "Arial", valign: "middle" });
  s.addText("Todas con fecha 2026-06. Las versiones futuras agregan ADR sin borrar las anteriores.",
    { x: 0.6, y: 6.55, w: 12, h: 0.3, fontSize: 9.5, color: MUTE, italic: true, fontFace: "Arial", margin: 0 });
  footer(s, 15);

  // ============================================================ S16 — Change log
  s = pres.addSlide(); s.background = { color: WHITE };
  header(s, ic.history, "Change log — control de versiones", "Trazabilidad");
  const cl = [
    ["Versión", "Fecha", "Resumen del cambio", "Estado del producto"],
    ["v1.0", "15-jun-26", "Línea base. Visión + 3 horizontes, alcance (8 épicas), arquitectura verificada en vivo, modelo de datos y máquina de estados, NFR, trazabilidad, roadmap, riesgos y ADR.", "Capa A lista; Capa B en calibración"],
    ["v1.1", "—", "(reservado) p. ej. cierre de Capa B con selectores reales tras la calibración.", "—"],
    ["v2.0", "—", "(reservado) p. ej. salto a H2 SaaS o cambio de arquitectura de datos.", "—"],
  ];
  const tc = cl.map((r, ri) => r.map((cell, ci) => {
    if (ri === 0) return { text: cell, options: { fill: { color: SLATE }, color: WHITE, bold: true, fontSize: 12, valign: "middle" } };
    const future = cell === "—" || (ri > 1);
    const base = { fontSize: 11, color: future && ci !== 0 ? MUTE : BODY, valign: "middle", fill: { color: ri === 1 ? TINT : WHITE }, italic: ri > 1 };
    if (ci === 0) return { text: cell, options: { ...base, bold: true, color: ri === 1 ? TEAL : MUTE, fontFace: "Courier New", italic: false } };
    return { text: cell, options: base };
  }));
  s.addTable(tc, { x: 0.6, y: 1.65, w: 12.13, colW: [1.3, 1.5, 6.43, 2.9], rowH: [0.5, 1.7, 1.0, 1.0], border: { type: "solid", pt: 0.5, color: LINE }, fontFace: "Arial", valign: "middle" });
  s.addText("Convención: el archivo lleva la versión en el nombre. Cada versión nueva apila una fila; las anteriores se conservan.",
    { x: 0.6, y: 6.6, w: 12, h: 0.3, fontSize: 9.5, color: MUTE, italic: true, fontFace: "Arial", margin: 0 });
  footer(s, 16);

  // ============================================================ S17 — Cierre
  s = pres.addSlide(); s.background = { color: SLATE };
  s.addShape(pres.shapes.OVAL, { x: -1.5, y: 5.0, w: 4.5, h: 4.5, fill: { color: TEALD, transparency: 55 } });
  s.addShape(pres.shapes.OVAL, { x: 11.4, y: -1.4, w: 3.4, h: 3.4, fill: { color: AMBER, transparency: 78 } });
  s.addImage({ data: ic.flag, x: 0.9, y: 1.3, w: 0.55, h: 0.55 });
  s.addText("Próximos pasos", { x: 1.6, y: 1.28, w: 10, h: 0.6, fontSize: 30, bold: true, color: WHITE, fontFace: "Arial", valign: "middle", margin: 0 });
  const ns = [
    ["1", "Calibrar la Capa B", "Correr calibrate_ficha.py en IP residencial; mapear el DOM real de la ficha."],
    ["2", "Cerrar download.py", "Con el DOM verificado, escribir navegación código→ficha→adjuntos + descarga + hash."],
    ["3", "Capa C post-gate", "Scoring Atlas + tablero con acceso a documentos. Solo después del gate."],
  ];
  let cy = 2.35;
  ns.forEach(([n, t, d]) => {
    s.addShape(pres.shapes.OVAL, { x: 1.0, y: cy, w: 0.5, h: 0.5, fill: { color: AMBER } });
    s.addText(n, { x: 1.0, y: cy, w: 0.5, h: 0.5, fontSize: 18, bold: true, color: SLATE, align: "center", valign: "middle", fontFace: "Arial", margin: 0 });
    s.addText([
      { text: t + "   ", options: { bold: true, color: WHITE, fontSize: 15 } },
      { text: d, options: { color: "CBD5E1", fontSize: 12 } },
    ], { x: 1.75, y: cy - 0.05, w: 10.6, h: 0.6, valign: "middle", fontFace: "Arial", margin: 0 });
    cy += 0.78;
  });
  card(s, 1.0, 4.95, 11.3, 1.15, "1E293B");
  s.addText([
    { text: "Recordatorio del Co-CEO:  ", options: { bold: true, color: AMBER } },
    { text: "el gate de julio se gana vendiendo, no construyendo. Este producto es palanca, no sustituto de la calle.", options: { color: WHITE } },
  ], { x: 1.35, y: 4.95, w: 10.7, h: 1.15, fontSize: 13.5, valign: "middle", fontFace: "Arial", lineSpacingMultiple: 1.05, margin: 0 });
  s.addText(`Loveo Licitaciones · Documento de Producto PO/BA · ${VER} · ${FECHA} · Interno`,
    { x: 0.9, y: 6.5, w: 11.5, h: 0.3, fontSize: 9, color: MUTE, fontFace: "Arial", margin: 0 });

  await pres.writeFile({ fileName: OUTFILE });
  console.log("OK deck escrito:", OUTFILE);
})();
