"""
run_daily.py — Orquestador diario (paga deuda 5 y 6: bookkeeping + manejo de errores).

Flujo:  descubrir -> filtrar -> [por cada candidato] detalle -> upsert -> admisibilidad
        -> scoring provisional (si admisible).  Registra la corrida en `runs`.

  python run_daily.py                 # procesa el día de hoy
  python run_daily.py 11062026        # un día puntual
  python run_daily.py --backfill 5    # los últimos 5 días hábiles no procesados
  python run_daily.py --cache dia.json 11062026   # modo test: usa un listado cacheado
"""
import os, sys, time, json
import db, discover, rules, scoring, extract, relicitaciones, notificar


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

    bases = None
    if os.environ.get("LOVEO_BASES_LOCAL"):   # carpeta madre local → registra bases nuevas para la Capa C
        try:
            import ingest_bases
            bases = ingest_bases.desde_local()
        except Exception as e:                # un fallo de ingesta NUNCA frena el pipeline
            bases = {"error": str(e)}
            try:
                import observabilidad
                observabilidad.capturar("run_daily.ingest_local", e)
            except Exception:
                pass

    try:
        avisos = notificar.correr()       # avisos de deadline; no-op si no hay SMTP configurado
    except Exception as e:                # un fallo de notificación NUNCA frena el pipeline
        avisos = {"error": str(e)}
        try:
            import observabilidad
            observabilidad.capturar("run_daily.notificar", e)
        except Exception:
            pass

    return {"fecha": fecha, "total": len(listado), "candidatos": len(candidatos),
            "admisibles": admisibles, "errores": errores, "relicitaciones": enlaces,
            "bases_local": bases, "avisos": avisos}


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


def _main():
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
        res = procesar_dia(fecha)
        # AUTO-CURACIÓN: además del día de hoy, recupera días hábiles que nunca se procesaron o
        # que se procesaron mal (la API falló y quedaron marcados como OK). Sin esto un día perdido
        # es invisible para siempre: se detectaron 62 licitaciones faltantes cruzando contra un
        # registro externo. Acotado por corrida — cada día es una llamada más a la API.
        if not args:
            res["cobertura"] = _curar_cobertura()
        print(json.dumps(res, indent=2, ensure_ascii=False))


def _curar_cobertura(limite=None):
    """Reprocesa los agujeros de cobertura detectados. Devuelve qué recuperó y qué queda."""
    import cobertura
    limite = cobertura.CURAR_POR_CORRIDA if limite is None else limite
    pendientes = cobertura.a_reprocesar(limite)
    recuperados = []
    for f in pendientes:
        try:
            r = procesar_dia(f)
            recuperados.append({"fecha": f, "total": r.get("total"), "candidatos": r.get("candidatos")})
        except Exception as e:
            recuperados.append({"fecha": f, "error": str(e)[:120]})
    e = cobertura.estado()
    return {"recuperados": recuperados, "huecos_restantes": e["huecos"], "pct": e["pct"]}


if __name__ == "__main__":
    try:
        _main()
    except Exception as e:   # un crash del cron diario no puede pasar desapercibido
        try:
            import observabilidad
            observabilidad.capturar("run_daily", e)
        except Exception:
            pass
        raise
