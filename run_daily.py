"""
run_daily.py — Orquestador diario (paga deuda 5 y 6: bookkeeping + manejo de errores).

Flujo:  descubrir -> filtrar -> [por cada candidato] detalle -> upsert -> admisibilidad
        -> scoring provisional (si admisible).  Registra la corrida en `runs`.

  python run_daily.py                 # procesa el día de hoy
  python run_daily.py 11062026        # un día puntual
  python run_daily.py --backfill 5    # los últimos 5 días hábiles no procesados
  python run_daily.py --cache dia.json 11062026   # modo test: usa un listado cacheado
"""
import sys, time, json
import db, discover, rules, scoring, extract, relicitaciones


def procesar_dia(fecha, listado=None, traer_detalles=True):
    db.init_db()
    if listado is None:
        listado = discover.listar_dia(fecha)
    candidatos = [x for x in listado if discover.matchea(x.get("Nombre", ""))]
    admisibles = errores = 0

    with db.conn() as c:
        for item in candidatos:
            codigo = item["CodigoExterno"]
            try:
                det = None
                if traer_detalles:
                    det = discover.traer_detalle(codigo)
                    row = discover._aplanar_detalle(det) if det else \
                          {"codigo": codigo, "nombre": item.get("Nombre"), "estado_mp": item.get("CodigoEstado")}
                    time.sleep(1.0)
                else:
                    row = {"codigo": codigo, "nombre": item.get("Nombre"), "estado_mp": item.get("CodigoEstado")}
                db.upsert_licitacion(c, row)
                if det:
                    extract.extraer(codigo, det, c=c)   # adjudicación/items/competidores/participaciones

                adm = rules.evaluar(row)
                db.set_admisibilidad(c, codigo, adm["admisible"], " | ".join(adm["motivos"]), adm["vigente"])
                if adm["admisible"] and row.get("region"):
                    sc = scoring.score_provisional(row)
                    db.set_score_provisional(c, codigo, sc["score_provisional"], json.dumps(sc, ensure_ascii=False),
                                             sc["requiere_bases"] or adm["requiere_bases"])
                    admisibles += 1
                elif adm["admisible"]:
                    admisibles += 1  # admisible pero sin región aún (detalle off)
            except Exception as e:
                errores += 1
                db.log_evento(c, codigo, "error", f"run_daily: {e}")
        db.record_run(c, fecha, len(listado), len(candidatos), admisibles, errores)

    enlaces = relicitaciones.detectar()   # enlaza desiertas con su re-licitación (conn propia)

    return {"fecha": fecha, "total": len(listado), "candidatos": len(candidatos),
            "admisibles": admisibles, "errores": errores, "relicitaciones": enlaces}


def procesar_codigo(codigo, manual=True):
    """Alta de UNA licitación por su código MP, salteando el filtro de keywords.
    Reusa el mismo flujo diario: detalle -> upsert -> extract -> admisibilidad -> score.
    Devuelve {ok, codigo, nombre, admisible, score, ya_existia} o {ok: False, error}.

      python run_daily.py --codigo 1509-12-LR26
    """
    codigo = (codigo or "").strip()
    if not codigo:
        return {"ok": False, "error": "Código vacío."}
    db.init_db()
    try:
        det = discover.traer_detalle(codigo)
    except Exception as e:
        return {"ok": False, "error": f"No se pudo consultar la API de Mercado Público: {e}"}
    if not det:
        return {"ok": False, "error": f"Mercado Público no devolvió datos para '{codigo}'. Revisá el código."}

    row = discover._aplanar_detalle(det)
    row.setdefault("codigo", codigo)
    with db.conn() as c:
        ya = c.execute("SELECT codigo FROM licitaciones WHERE codigo=?", (row["codigo"],)).fetchone() is not None
        db.upsert_licitacion(c, row)
        try:
            extract.extraer(row["codigo"], det, c=c)
        except Exception as e:
            db.log_evento(c, row["codigo"], "error", f"extract (alta manual): {e}")
        adm = rules.evaluar(row)
        db.set_admisibilidad(c, row["codigo"], adm["admisible"], " | ".join(adm["motivos"]), adm["vigente"])
        score = None
        if adm["admisible"] and row.get("region"):
            try:
                sc = scoring.score_provisional(row)
                db.set_score_provisional(c, row["codigo"], sc["score_provisional"],
                                         json.dumps(sc, ensure_ascii=False),
                                         sc["requiere_bases"] or adm["requiere_bases"])
                score = sc["score_provisional"]
            except Exception as e:
                db.log_evento(c, row["codigo"], "error", f"scoring (alta manual): {e}")
        if manual:
            db.log_evento(c, row["codigo"], "agregada_manual",
                          "alta manual por código" + (" (ya existía, actualizada)" if ya else ""))
    return {"ok": True, "codigo": row["codigo"], "nombre": row.get("nombre"),
            "admisible": bool(adm["admisible"]), "score": score, "ya_existia": ya}


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--cache" in args:
        i = args.index("--cache")
        listado = json.load(open(args[i + 1]))["Listado"]
        fecha = args[i + 2] if len(args) > i + 2 else time.strftime("%d%m%Y")
        print(json.dumps(procesar_dia(fecha, listado=listado, traer_detalles=False), indent=2, ensure_ascii=False))
    elif "--codigo" in args:
        codigo = args[args.index("--codigo") + 1]
        print(json.dumps(procesar_codigo(codigo), indent=2, ensure_ascii=False))
    elif "--backfill" in args:
        n = int(args[args.index("--backfill") + 1])
        db.init_db()
        with db.conn() as c:
            hechas = db.fechas_procesadas(c)
        hoy = time.time(); done = 0; d = 0
        while done < n and d < 30:
            t = time.localtime(hoy - d * 86400)
            if t.tm_wday < 5:  # hábil
                f = time.strftime("%d%m%Y", t)
                if f not in hechas:
                    print(json.dumps(procesar_dia(f), ensure_ascii=False)); done += 1
            d += 1
    else:
        fecha = args[0] if args else time.strftime("%d%m%Y")
        print(json.dumps(procesar_dia(fecha), indent=2, ensure_ascii=False))
