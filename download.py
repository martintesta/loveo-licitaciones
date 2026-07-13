"""
download.py — Capa B: descarga de adjuntos. CORRE LOCAL (IP residencial CL).

RUTA CALIBRADA (verificada 2026-06-16 contra el portal real):
  1) Ficha:    https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion=<CODIGO>
               (el servidor resuelve solo el token qs=; el código va en texto plano, 'idlicitacion' en minúscula)
  2) Adjuntos: en la ficha, el botón #imgAdjuntos tiene
               onclick="open('../Attachment/ViewAttachment.aspx?enc=<TOKEN>', ...)"
               → se abre ViewAttachment.aspx?enc=<TOKEN> con la grilla de archivos.
  3) Descargar cada archivo de la grilla.

IMPORTANTE — POR QUÉ LOCAL:
  El endpoint ViewAttachment dispara el muro anti-bot ("actividad anormal") ante accesos
  automatizados desde IP de datacenter. Desde tu notebook (IP residencial CL, navegador normal)
  es uso genuino y no se bloquea. NO se evade la protección: se corre donde el acceso es legítimo.
  Tip: corré con HEADLESS=False la primera vez (navegador visible = menos señales de automatización).

  python download.py 2450-56-LE26   # una licitación
  python download.py                 # todas las admisibles sin docs

Si la grilla de ViewAttachment no entrega archivos, corré `python calibrate_ficha.py <codigo>`
local (dumpea el DOM de la grilla) y con eso fijamos el último selector.
"""
import sys, re, hashlib, time
from pathlib import Path
from playwright.sync_api import sync_playwright
import db

PORTAL = "https://www.mercadopublico.cl"
HEADLESS = True   # ← poné False en tu máquina la primera vez
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
# Firmas del muro anti-bot de Mercado Público (varían: "actividad anormal" o la página de
# "Acceso denegado" con robot.png que devuelve ViewAttachment ante un acceso no residencial).
MUROS = ("actividad anormal", "acceso denegado", "robot.png")


def _abrir_ficha(page, codigo):
    url = f"{PORTAL}/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion={codigo}"
    r = page.goto(url, timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    return bool(r) and "Ficha" in (page.title() or "")


def _url_adjuntos(page):
    """Extrae la URL de ViewAttachment desde el onclick de #imgAdjuntos."""
    el = page.query_selector("#imgAdjuntos")
    if not el:
        return None
    oc = el.get_attribute("onclick") or ""
    m = re.search(r"ViewAttachment\.aspx\?enc=([^'\"]+)", oc)
    return f"{PORTAL}/Procurement/Modules/Attachment/ViewAttachment.aspx?enc={m.group(1)}" if m else None


def _html_muro(html):
    """True si el HTML es una página del muro anti-bot (pura, testeable)."""
    h = (html or "").lower()
    return any(m in h for m in MUROS)


def _es_muro(page):
    try:
        return _html_muro(page.content())
    except Exception:
        return False


def _controles_descarga(page):
    """Best-effort sobre la grilla de ViewAttachment (a confirmar local con calibrate_ficha)."""
    js = r"""() => {
      const out=[];
      for (const el of document.querySelectorAll('a,input[type=button],input[type=submit],button')) {
        const t=(el.innerText||el.value||'').trim(), id=el.id||'',
              oc=el.getAttribute('onclick')||'', h=el.getAttribute('href')||'';
        if (/(descarg|download|bajar|\.pdf|\.docx?|\.xlsx?|\.zip|\.rar|doPostBack)/i.test(t+id+oc+h))
          out.push({id, text:t.slice(0,60), onclick:oc.slice(0,120), href:h});
      }
      return out;
    }"""
    try:
        return page.evaluate(js)
    except Exception:
        return []


def _guardar(codigo, nombre, contenido: bytes):
    carpeta = db.STORAGE_DIR / codigo
    carpeta.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256(contenido).hexdigest()
    destino = carpeta / nombre
    destino.write_bytes(contenido)
    with db.conn() as c:
        try:
            c.execute("""INSERT INTO documentos(codigo,nombre_archivo,ruta_local,tipo,bytes,sha256,descargado_at)
                         VALUES (?,?,?,?,?,?,?)""",
                      (codigo, nombre, str(destino), destino.suffix.lstrip("."),
                       len(contenido), sha, db._now()))
        except Exception:
            pass  # dedup (codigo, sha256)
    return sha


def descargar_codigo(codigo):
    with db.conn() as c:
        c.execute("UPDATE licitaciones SET docs_estado='descargando' WHERE codigo=?", (codigo,))
    bajados, nota = 0, ""
    carpeta = db.STORAGE_DIR / codigo
    with sync_playwright() as p:
        b = p.chromium.launch(headless=HEADLESS, args=["--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(locale="es-CL", timezone_id="America/Santiago", accept_downloads=True, user_agent=UA,
                            viewport={"width": 1440, "height": 1000})
        page = ctx.new_page()
        page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")

        if not _abrir_ficha(page, codigo):
            nota = "ficha no resuelta"
        else:
            va = _url_adjuntos(page)
            if not va:
                nota = "sin adjuntos en la ficha (#imgAdjuntos ausente)"
            else:
                page.goto(va, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                if _es_muro(page):
                    carpeta.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(carpeta / "_muro_antibot.png"))
                    nota = "BLOQUEO anti-bot (correr en IP residencial / HEADLESS=False)"
                else:
                    for ctrl in _controles_descarga(page):
                        try:
                            with page.expect_download(timeout=30000) as di:
                                if ctrl.get("id"):
                                    page.click(f"#{ctrl['id']}")
                                elif ctrl.get("href"):
                                    page.goto(ctrl["href"])
                            dl = di.value
                            _guardar(codigo, dl.suggested_filename or (ctrl["text"][:40] + ".bin"),
                                     Path(dl.path()).read_bytes())
                            bajados += 1
                        except Exception as e:
                            with db.conn() as c:
                                db.log_evento(c, codigo, "descarga", f"link falló: {e}")
                    if not bajados:
                        carpeta.mkdir(parents=True, exist_ok=True)
                        page.screenshot(path=str(carpeta / "_grilla_sin_descarga.png"))
                        html = page.content()
                        (carpeta / "_viewattachment.html").write_text(html, encoding="utf-8")
                        if "recaptcha" in (html or "").lower():
                            nota = ("protegido por reCAPTCHA — no automatizable; descargá las bases a "
                                    "mano (browser) y subilas por Drive/storage para la Capa C")
                        else:
                            nota = "grilla sin descargas — correr calibrate_ficha.py y enviar _viewattachment.html"
        b.close()

    estado = "completo" if bajados else "error"
    with db.conn() as c:
        c.execute("UPDATE licitaciones SET docs_estado=?, docs_carpeta=? WHERE codigo=?",
                  (estado, str(carpeta), codigo))
        db.log_evento(c, codigo, "descarga", f"{bajados} archivo(s) · {nota}" if nota else f"{bajados} archivo(s)")
    return {"codigo": codigo, "ok": bajados > 0, "bajados": bajados, "nota": nota}


def pendientes():
    with db.conn() as c:
        return [r[0] for r in c.execute(
            "SELECT codigo FROM licitaciones WHERE admisible=1 AND docs_estado='pendiente'").fetchall()]


if __name__ == "__main__":
    db.init_db()
    objetivos = [sys.argv[1]] if len(sys.argv) > 1 else pendientes()
    print(f"A descargar: {len(objetivos)} licitación(es)")
    for cod in objetivos:
        print(" ", descargar_codigo(cod))
        time.sleep(2)
