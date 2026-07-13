"""
calibrate_ficha.py — SONDA LOCAL para cerrar el ÚLTIMO selector de la Capa B.

Estado de la calibración (hecha el 2026-06-16 contra el portal real):
  ✅ Ficha:    DetailsAcquisition.aspx?idlicitacion=<CODIGO>  (resuelve solo el token qs=)
  ✅ Adjuntos: #imgAdjuntos → onclick open('../Attachment/ViewAttachment.aspx?enc=<TOKEN>')
  ❓ Grilla de ViewAttachment: los nombres de archivo y el control de descarga.
     No se pudo mapear desde datacenter porque ViewAttachment dispara el muro anti-bot
     ("actividad anormal"). Desde tu IP residencial NO se bloquea: por eso esta sonda la corrés vos.

QUÉ HACE (en tu máquina):
  1. Abre la ficha del código → extrae la URL de ViewAttachment.
  2. Abre ViewAttachment y dumpea su DOM + screenshot en ./calibration/.
  3. Lista filas de archivos y controles de descarga candidatos.
  4. Avisa si apareció el muro anti-bot (si pasa, probá HEADLESS=False).

CÓMO CORRER:
    pip install playwright
    python -m playwright install chromium
    python calibrate_ficha.py 2450-56-LE26
  Mandame ./calibration/viewattachment.html (y el screenshot) y fijo el selector final
  en download.py. Si HEADLESS=True te da el muro, cambialo a False (navegador visible).
"""
import sys, re, json
from pathlib import Path
from playwright.sync_api import sync_playwright

HEADLESS = True          # ← si aparece el muro anti-bot, poné False
OUT = Path(__file__).parent / "calibration"; OUT.mkdir(exist_ok=True)
PORTAL = "https://www.mercadopublico.cl"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def main(codigo):
    print(f"\n=== Calibración ViewAttachment para {codigo} ===")
    with sync_playwright() as p:
        b = p.chromium.launch(headless=HEADLESS, args=["--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(locale="es-CL", timezone_id="America/Santiago", accept_downloads=True,
                            user_agent=UA, viewport={"width": 1440, "height": 1000})
        page = ctx.new_page()
        page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")

        ficha = f"{PORTAL}/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion={codigo}"
        page.goto(ficha, timeout=60000, wait_until="domcontentloaded"); page.wait_for_timeout(4000)
        print(" ficha:", page.title())
        el = page.query_selector("#imgAdjuntos")
        if not el:
            print(" ‼ No hay #imgAdjuntos (¿licitación sin adjuntos?). Fin."); b.close(); return
        m = re.search(r"ViewAttachment\.aspx\?enc=([^'\"]+)", el.get_attribute("onclick") or "")
        if not m:
            print(" ‼ No se pudo extraer el token enc."); b.close(); return
        va = f"{PORTAL}/Procurement/Modules/Attachment/ViewAttachment.aspx?enc={m.group(1)}"

        page.goto(va, timeout=60000, wait_until="domcontentloaded"); page.wait_for_timeout(3500)
        html = page.content()
        page.screenshot(path=str(OUT / "viewattachment.png"), full_page=True)
        (OUT / "viewattachment.html").write_text(html, encoding="utf-8")

        import download
        if download._html_muro(html):
            print(" ‼ MURO ANTI-BOT (p.ej. 'Acceso denegado' / robot.png). Este endpoint bloquea el"
                  " acceso: confirmá que estás en IP residencial chilena (no VPN/red corporativa) y"
                  " probá con HEADLESS=False."); b.close(); return

        data = page.evaluate(r"""()=>{
          const ctrls=[];
          for(const el of document.querySelectorAll('a,input[type=button],input[type=submit],button')){
            const t=(el.innerText||el.value||'').trim(),id=el.id||'',oc=el.getAttribute('onclick')||'',h=el.getAttribute('href')||'';
            if(/(descarg|download|bajar|\.pdf|\.docx?|\.xlsx?|\.zip|doPostBack)/i.test(t+id+oc+h))
              ctrls.push({tag:el.tagName,id,text:t.slice(0,60),onclick:oc.slice(0,120),href:h.slice(0,120)});
          }
          const nombres=[...document.querySelectorAll('td,span,a,div')].map(e=>(e.innerText||'').trim())
            .filter(t=>/\.(pdf|docx?|xlsx?|zip|rar)$/i.test(t));
          return {controles:ctrls.slice(0,40), nombres:[...new Set(nombres)].slice(0,40)};
        }""")
        print(f" archivos detectados: {data['nombres']}")
        print(f" controles de descarga: {len(data['controles'])}")
        for c in data["controles"][:15]: print("   ", c)
        (OUT / "viewattachment_controles.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"\n Listo. Mandame: {OUT/'viewattachment.html'}")
        b.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "2450-56-LE26")
