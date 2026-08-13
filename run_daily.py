"""
run_daily.py — Orquestador diario (paga deuda 5 y 6: bookkeeping + manejo de errores).

Flujo:  descubrir -> filtrar -> [por cada candidato] detalle -> upsert -> admisibilidad
        -> scoring provisional (si admisible).  Registra la corrida en `runs`.

  python run_daily.py                 # procesa AYER (hoy todavía se está publicando)
  python run_daily.py 11062026        # un día puntual
  python run_daily.py --backfill 5    # los últimos 5 días hábiles no procesados
  python run_daily.py --cache dia.json 11062026   # modo test: usa un listado cacheado
"""
import os, sys, time, json
import db, discover, rules, scoring, extract, relicitaciones, notificar


def _ayer():
    """El día hábil que el cron barre por defecto: AYER, no hoy.

    Antes barría `time.strftime('%d%m%Y')` = hoy, y el cron corre a las 08:00. A esa hora Mercado
    Público todavía no publicó casi nada del día: los runs quedaban con 3, 4 y 16 licitaciones
    contra las 1.142, 1.385 y 1.201 que la API devuelve para esos mismos días una vez cerrados.
    O sea que cada corrida diaria FABRICABA un día sospechoso nuevo, y el auto-curador (que
    recupera 3 por corrida) estaba apagando incendios que el propio cron encendía.

    Sábado y domingo no se saltean: la ventana de cobertura solo audita días hábiles, así que un
    barrido de fin de semana no ensucia nada y sirve para pescar publicaciones tardías."""
    return time.strftime("%d%m%Y", time.localtime(time.time() - 86400))


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

    # SEGUNDA PASADA: las que el título esconde. El listado diario sólo trae el nombre, así que
    # una licitación cuyo producto está en la descripción no llega nunca al filtro. Caso real:
    # "ADQUIS E INST PUNTO DE SEGURIDAD AMERICO VESPUCIO" (Recoleta, $15,0M) era un container
    # habilitado como oficina — la palabra "container" sólo aparecía en la descripción.
    rescatadas = []
    if traer_detalles and listado and os.environ.get("LOVEO_SEGUNDA_PASADA", "1") == "1":
        try:
            rescatadas = _segunda_pasada(listado, {x["CodigoExterno"] for x in candidatos}, c=None)
        except Exception as e:
            rescatadas = [{"error": str(e)[:120]}]
            try:
                import observabilidad
                observabilidad.capturar("run_daily.segunda_pasada", e)
            except Exception:
                pass

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

    # Ventana de visita a terreno. Va DESPUÉS de la ingesta a propósito: las que quedan sin bases
    # después de intentar ingestarlas son exactamente las que no podemos leer, y por lo tanto
    # aquellas de las que no sabemos si convocan visita. El silencio no es "no hay visita".
    visita = None
    try:
        import visitas
        visita = {"sin_bases_en_riesgo": visitas.en_riesgo(),
                  "con_visita_abierta": visitas.pendientes_de_visita()}
    except Exception as e:                # un fallo de la alerta NUNCA frena el pipeline
        visita = {"error": str(e)}
        try:
            import observabilidad
            observabilidad.capturar("run_daily.visitas", e)
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
            "rescatadas": rescatadas, "bases_local": bases, "visita_terreno": visita,
            "avisos": avisos}


MAX_SEGUNDA_PASADA = int(os.environ.get("LOVEO_MAX_SEGUNDA_PASADA", "150"))


def _segunda_pasada(listado, ya, c=None):
    """Pide el detalle de las que el título no delata y las pasa por el embudo.

    Sobre un listado real de 1.186: 13 matchean por título, 337 quedan como candidatas tras el
    filtro barato. Acotado por MAX_SEGUNDA_PASADA porque cada una es una llamada al API — el
    tope se gasta primero en lo que cierra más lejos, que es lo que todavía se puede trabajar.

    Devuelve sólo las RESCATADAS: las que el embudo aprueba y por lo tanto valen un alta."""
    import discover as disc
    import triage
    cands = disc.candidatas_segunda_pasada(listado, ya)[:MAX_SEGUNDA_PASADA]
    rescatadas = []
    for item in cands:
        cod = item.get("CodigoExterno")
        try:
            det = discover.traer_detalle(cod)
            time.sleep(1.0)
        except Exception:
            continue
        if not det:
            continue
        row = discover._aplanar_detalle(det)
        row["json_detalle"] = json.dumps(det, ensure_ascii=False)
        g = triage.gate_producto(row)
        if not g["pasa"]:
            continue
        r = procesar_codigo(cod, manual=False)      # alta completa: upsert + extract + score
        if r.get("ok"):
            rescatadas.append({"codigo": cod, "nombre": row.get("nombre"),
                               "senal": g["senal"], "confianza": g["confianza"],
                               "score": r.get("score")})
    return rescatadas


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
        fecha = args[0] if args else _ayer()
        res = procesar_dia(fecha)
        # AUTO-CURACIÓN: además del día de hoy, recupera días hábiles que nunca se procesaron o
        # que se procesaron mal (la API falló y quedaron marcados como OK). Sin esto un día perdido
        # es invisible para siempre: se detectaron 62 licitaciones faltantes cruzando contra un
        # registro externo. Acotado por corrida — cada día es una llamada más a la API.
        if not args:
            res["cobertura"] = _curar_cobertura()
            res["sin_detalle"] = _curar_sin_detalle()
        print(json.dumps(res, indent=2, ensure_ascii=False))


CURAR_SIN_DETALLE_POR_CORRIDA = int(os.environ.get("LOVEO_CURAR_SIN_DETALLE", "15"))


def _curar_sin_detalle(limite=None):
    """Completa las licitaciones que quedaron a medias: sin `json_detalle`, o sin fecha de cierre.

    `procesar_dia(traer_detalles=False)` (modo caché, o un día en que la API de detalle falló) las
    da de alta sólo con código y nombre. Sin fecha de cierre NINGÚN filtro las saca: quedan
    'vigentes' para siempre y aparecen en los listados como si estuvieran abiertas. Se encontraron
    dos así, de junio de 2026 — una de $160M con score 80 que nadie miró porque parecía ruido.

    Es el mismo patrón que la visita a terreno: un dato que FALTA se lee como 'todo bien' en vez
    de como 'no sabemos'. Acotado por corrida: cada una es una llamada a la API."""
    limite = CURAR_SIN_DETALLE_POR_CORRIDA if limite is None else limite
    db.init_db()
    with db.conn() as c:
        pendientes = [r["codigo"] for r in c.execute(
            "SELECT codigo FROM licitaciones "
            "WHERE (json_detalle IS NULL OR fecha_cierre IS NULL) AND vigente_oferta=1 "
            "ORDER BY fecha_descubierta DESC LIMIT ?", (limite,)).fetchall()]
    completadas, fallidas = [], []
    for cod in pendientes:
        try:
            r = procesar_codigo(cod, manual=False)
            if r.get("ok"):
                completadas.append({"codigo": cod, "score": r.get("score")})
            else:
                fallidas.append({"codigo": cod, "error": (r.get("error") or "")[:100]})
        except Exception as e:                 # una licitación que falla no frena la curación
            fallidas.append({"codigo": cod, "error": str(e)[:100]})
        time.sleep(1.0)                        # mismo respeto por la API que en procesar_dia
    with db.conn() as c:
        quedan = c.execute(
            "SELECT COUNT(*) n FROM licitaciones "
            "WHERE (json_detalle IS NULL OR fecha_cierre IS NULL) AND vigente_oferta=1").fetchone()["n"]
    return {"completadas": completadas, "fallidas": fallidas, "pendientes": quedan}


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
