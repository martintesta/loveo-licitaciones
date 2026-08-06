"""
plan.py — Motor "Plan del día" / próxima mejor acción (epic plan-del-dia, Fase 1).

Compone las señales que ya arma build_data (score × confianza, días al cierre, visita obligatoria,
estado en el embudo, si falta la cubicación, análisis de bases) en una COLA PRIORIZADA DE ACCIONES,
cada una con su porqué. Puro (lics → acciones), sin DB: el usuario ve QUÉ HACER PRIMERO sin tener
que decidirlo él. Es una sugerencia; no ejecuta nada.

  construir(lics, hoy=None, limite=12) -> [{tipo, codigo, titulo, motivo, prioridad, dias}] ordenada
"""

# Pesos/umbrales (sobreescribibles desde config_local.py). La prioridad de cada acción es
#   valor (score×confianza) + urgencia (por deadline) + tipo (los atados a deadline arriba).
try:
    from config import PLAN_UMBRAL_CIERRE as UMBRAL_CIERRE
except (ImportError, AttributeError):
    UMBRAL_CIERRE = 10          # días: mirar cierres dentro de esta ventana
try:
    from config import PLAN_UMBRAL_VISITA as UMBRAL_VISITA
except (ImportError, AttributeError):
    UMBRAL_VISITA = 14          # días: mirar visitas dentro de esta ventana
try:
    from config import PLAN_PESO_URGENCIA as PESO_URGENCIA
except (ImportError, AttributeError):
    PESO_URGENCIA = 60          # cuánto suma la cercanía del deadline (máximo)
try:
    from config import PLAN_TIPO_BOOST as TIPO_BOOST
except (ImportError, AttributeError):
    TIPO_BOOST = {"VISITA": 45, "PRESENTAR": 35, "CIERRE": 22, "CUBICAR": 15, "REVISAR": 6, "BASES": 6}
try:
    from config import PLAN_PESO_PREF as PESO_PREF
except (ImportError, AttributeError):
    PESO_PREF = 25              # cuánto puede sumar la preferencia APRENDIDA (tope total, no por eje)
try:
    from config import PLAN_DIAS_PREF as DIAS_PREF
except (ImportError, AttributeError):
    DIAS_PREF = 90             # ventana de comportamiento reciente para las preferencias
try:
    from config import PLAN_K_CONFIANZA as K_CONFIANZA
except (ImportError, AttributeError):
    K_CONFIANZA = 10           # cuánta evidencia hace falta para acercarse al tope (n/(n+K))

# Acciones que cuentan como "el usuario invirtió atención EN PERSEGUIR esta lic" (preferencia, Fase 3).
# Deliberadamente NO incluyen:
#  - rep_pago: es un juicio sobre el comprador (puede ser MALO). Marcarlo como mal pagador subía su
#    preferencia → el plan priorizaba al comprador que se quiere evitar (señal invertida). La
#    reputación ya entra al score por su propia vía (comprador.reputaciones en build_data).
#  - capac: es solo el PREVIEW de costo; el usuario puede mirarlo y cancelar. El análisis real
#    (capac_run) sí cuenta.
ENGAGEMENT_ACTS = {"seguir", "aprobar", "capac_run", "cubic_ia", "cubic_guardar",
                   "cubic_preciar", "cubic_margen", "cubic_receta"}

_ESTRES = {  # etiqueta corta por tipo (para la UI)
    "VISITA": "Visita", "PRESENTAR": "Presentar", "CIERRE": "Cierre", "CUBICAR": "Cubicar",
    "REVISAR": "Revisar", "BASES": "Bases",
}


def _activa(l):
    """En juego: ni descartada, ni ya presentada/cerrada, ni con el cierre ya pasado."""
    if l.get("dias") is not None and l.get("dias") < 0:
        return False                                     # el cierre ya pasó: no hay nada que hacer
    return l.get("estRev") != "descartada" and (l.get("estRes") in (None, "", "pendiente"))


def _valor(l):
    """Valor de la lic: score ponderado por su confianza (dimensiones con dato real)."""
    sc = l.get("score")
    if sc is None:
        return 0.0
    nd = l.get("nDims") or 6
    ev = l.get("evDims")
    conf = (ev / nd) if (ev is not None and nd) else 0.5
    return sc * conf


def _urgencia(dias, umbral):
    """0..PESO_URGENCIA: cuanto más cerca el deadline, más urgente. None si no aplica."""
    if dias is None or dias < 0 or dias > umbral:
        return None
    return round(PESO_URGENCIA * (umbral - dias) / umbral, 1)


def _tiene_bases(l):
    return bool(l.get("analisis"))


def _margen_hecho(l):
    """El margen ya está evaluado (la dimensión margen del score dejó de ser neutro)."""
    for d in (l.get("dims") or []):
        if d.get("n", "").lower().startswith("marg"):
            return bool(d.get("ev"))
    return False


def _accion_de(l):
    """La ÚNICA acción más pertinente para una lic (o None). Precedencia: visita > cierre > revisar."""
    cod, nom = l.get("cod"), (l.get("nom") or "—")
    dv, dc = l.get("diasVisita"), l.get("dias")
    sc = l.get("score")

    uv = _urgencia(dv, UMBRAL_VISITA)
    if uv is not None:                                   # visita obligatoria próxima → lo más crítico
        cuando = "HOY" if dv == 0 else "mañana" if dv == 1 else f"en {dv} días"
        return _mk("VISITA", cod, nom, f"Visita a terreno {cuando} — agendala/andá (si la perdés, "
                   f"quedás afuera).", l, uv, dv)

    uc = _urgencia(dc, UMBRAL_CIERRE)
    if uc is not None:                                   # cierra pronto → según en qué punto está
        cuando = "HOY" if dc == 0 else "mañana" if dc == 1 else f"en {dc} días"
        if l.get("estRev") == "aprobada":
            return _mk("PRESENTAR", cod, nom, f"Aprobada y cierra {cuando} — preparala y presentá.", l, uc, dc)
        if _tiene_bases(l) and not _margen_hecho(l):
            return _mk("CUBICAR", cod, nom, f"Cierra {cuando} y falta la cubicación — cargala para el "
                       f"GO/NO-GO.", l, uc, dc)
        if l.get("estRev") == "nueva":
            return _mk("REVISAR", cod, nom, f"Cierra {cuando} y todavía sin revisar — decidí ya.", l, uc, dc)
        return _mk("CIERRE", cod, nom, f"En juego y cierra {cuando}.", l, uc, dc)

    # Sin deadline inmediato: nuevas fit valiosas para triage, o cubicación pendiente.
    if l.get("estRev") == "nueva" and l.get("tri") in ("Priorizar", "Revisar"):
        return _mk("REVISAR", cod, nom, f"Nueva fit sin revisar (score {sc}) — revisá para decidir.", l, None, dc)
    if l.get("estRev") in ("en_revision", "aprobada") and _tiene_bases(l) and not _margen_hecho(l):
        return _mk("CUBICAR", cod, nom, "Bases leídas, falta la cubicación para cerrar el margen.", l, None, dc)
    if l.get("estRev") in ("en_revision", "aprobada") and not _tiene_bases(l) and l.get("tri") in ("Priorizar", "Revisar"):
        return _mk("BASES", cod, nom, f"La seguís (score {sc}) pero sin bases analizadas — conseguí las "
                   f"bases (Drive) para poder decidir.", l, None, dc)
    return None


def _mk(tipo, cod, nom, motivo, l, urgencia, dias):
    prioridad = round(_valor(l) + (urgencia or 0) + TIPO_BOOST.get(tipo, 0), 1)
    return {"tipo": tipo, "etiqueta": _ESTRES[tipo], "codigo": cod, "titulo": nom,
            "motivo": motivo, "prioridad": prioridad, "dias": dias,
            "score": l.get("score"), "regc": l.get("regc"), "org": l.get("org")}


def _pref_boost(l, prefs):
    """Suma de la preferencia aprendida por comprador + región + tipo de producto (Fase 3)."""
    if not prefs:
        return 0.0
    b = prefs.get("organismo", {}).get(l.get("org") or "", 0)
    b += prefs.get("region", {}).get(l.get("reg") or "", 0)
    b += prefs.get("tipo", {}).get(l.get("tipoProd") or "", 0)
    # Acotado en AMBOS sentidos: empuja pero no aplasta un deadline real, y un rechazo hunde
    # pero no saca del plan algo que cierra mañana.
    return max(-PESO_PREF, min(b, PESO_PREF))


def construir(lics, hoy=None, limite=12, prefs=None):
    """Cola priorizada de acciones a partir del `lics` de build_data. `prefs` (de preferencias())
    sube lo que el usuario efectivamente ataca — comprador/región/tipo (Fase 3). Puro."""
    acciones = []
    for l in (lics or {}).values():
        if not _activa(l):
            continue
        a = _accion_de(l)
        if a:
            a["prioridad"] = round(a["prioridad"] + _pref_boost(l, prefs), 1)
            acciones.append(a)
    acciones.sort(key=lambda a: a["prioridad"], reverse=True)
    return acciones[:limite]


# ---------------------------------------------------------------- Fase 3: aprender del comportamiento
def _usuario_id(u):
    """Nombre de usuario como TEXTO. El user de sesión de la UI es un dict
    {username, nombre, rol}: bindearlo crudo reventaba SQLite ("type 'dict' is not supported")
    y tiraba TODO el tablero. Acepta str, dict o None."""
    if u is None:
        return None
    if isinstance(u, dict):
        u = u.get("username")
    return str(u) if u else None


def es_engagement(act):
    """True si la acción indica que el usuario invirtió atención (alimenta la preferencia)."""
    return act in ENGAGEMENT_ACTS or (act or "").startswith("resultado:")


def registrar_engagement(codigo, usuario=None, senal="engagement", peso=1.0, motivo=None):
    """Registra una SEÑAL de aprendizaje sobre `codigo` (toma comprador/región/tipo del propio código).
    No lanza si el código no existe.

    `senal`/`peso` tipan la evidencia — no toda vale lo mismo ni toda es positiva:
      engagement  (+1)  el usuario invirtió atención (la más débil, pero llega a diario)
      correccion  (+2)  corrigió una estimación del sistema: dice QUÉ estaba mal, no solo qué le importa
      alta_manual (+2)  se tomó el trabajo de traerla a mano: intención deliberada
      rechazo     (−2)  la descartó del plan con motivo: evidencia EN CONTRA
    """
    import db
    import schema_v3
    import cubicacion_ia
    schema_v3.migrate()
    usuario = _usuario_id(usuario)
    with db.conn() as c:
        r = c.execute("SELECT organismo, region, nombre FROM licitaciones WHERE codigo=?",
                      (codigo,)).fetchone()
        if not r:
            return
        tp = cubicacion_ia.tipo_producto(r["nombre"] or "")
        c.execute("INSERT INTO plan_feedback (codigo, organismo, region, tipo_producto, usuario, "
                  "senal, peso, motivo, ts) VALUES (?,?,?,?,?,?,?,?,?)",
                  (codigo, r["organismo"], r["region"], tp, usuario, senal, float(peso), motivo,
                   db._now()))


# Peso por tipo de señal. La corrección y el alta manual valen más que un click; el rechazo resta.
PESOS_SENAL = {"engagement": 1.0, "correccion": 2.0, "alta_manual": 2.0, "rechazo": -2.0}


def registrar_correccion(codigo, usuario=None, motivo=None):
    """El usuario corrigió una estimación del sistema (ej.: cambió cantidades de la cubicación IA).
    Es la señal más informativa que existe y llega el mismo día."""
    registrar_engagement(codigo, usuario, "correccion", PESOS_SENAL["correccion"], motivo)


def registrar_rechazo(codigo, usuario=None, motivo=None):
    """El usuario sacó una acción del plan con un motivo. Evidencia NEGATIVA: baja compradores,
    regiones y tipos que no quiere ver arriba."""
    registrar_engagement(codigo, usuario, "rechazo", PESOS_SENAL["rechazo"], motivo)


def backfill_desde_eventos(usuario=None):
    """Reconstruye señal de aprendizaje desde `eventos`, que ya registra decisiones humanas desde
    antes de que existiera plan_feedback. Sin esto el motor arranca en cero teniendo historia.

    Traduce:
      agregada_manual  -> alta_manual (+2)   se tomó el trabajo de traerla: intención deliberada
      cambio_estado    -> según a dónde movió la licitación (aprobada/en_revision suman, descartada resta)

    Idempotente: no re-inserta una señal ya reconstruida (misma licitación, señal y timestamp).
    Devuelve el conteo por tipo de señal."""
    import db
    import schema_v3
    import cubicacion_ia
    schema_v3.migrate()
    usuario = _usuario_id(usuario)
    hechos = {"alta_manual": 0, "engagement": 0, "rechazo": 0, "omitidos": 0}
    with db.conn() as c:
        ya = {(r["codigo"], r["senal"], r["ts"]) for r in
              c.execute("SELECT codigo, senal, ts FROM plan_feedback").fetchall()}
        lics = {r["codigo"]: r for r in
                c.execute("SELECT codigo, organismo, region, nombre FROM licitaciones").fetchall()}
        evs = c.execute("SELECT codigo, tipo, detalle, ts FROM eventos "
                        "WHERE tipo IN ('agregada_manual','cambio_estado') ORDER BY ts").fetchall()
        for e in evs:
            lic = lics.get(e["codigo"])
            if not lic:
                hechos["omitidos"] += 1
                continue
            det = (e["detalle"] or "").lower()
            if e["tipo"] == "agregada_manual":
                senal = "alta_manual"
            elif "descartada" in det:
                senal = "rechazo"
            elif "aprobada" in det or "en_revision" in det:
                senal = "engagement"
            else:
                hechos["omitidos"] += 1
                continue
            if (e["codigo"], senal, e["ts"]) in ya:
                continue
            tp = cubicacion_ia.tipo_producto(lic["nombre"] or "")
            c.execute("INSERT INTO plan_feedback (codigo, organismo, region, tipo_producto, usuario, "
                      "senal, peso, motivo, ts) VALUES (?,?,?,?,?,?,?,?,?)",
                      (e["codigo"], lic["organismo"], lic["region"], tp, usuario, senal,
                       PESOS_SENAL[senal], (e["detalle"] or "")[:200], e["ts"]))
            hechos[senal] += 1
    return hechos


def preferencias(usuario=None, detalle=False):
    """Preferencia aprendida por eje (comprador/región/tipo), en [-PESO_PREF, +PESO_PREF].

    La evidencia SE GANA: el aporte de cada clave se pondera por su confianza `n/(n+K_CONFIANZA)`,
    donde n es la cantidad de decisiones que la respaldan. Antes se normalizaba dividiendo por el
    máximo, así que **una sola decisión se llevaba el tope completo** (era el máximo de su propio
    conjunto): un click valía tanto como cincuenta. Con K=10: 3 decisiones ≈ 23% del tope,
    12 ≈ 55%, 36 ≈ 78%.

    El peso es CON SIGNO: un rechazo con motivo baja al comprador en vez de solo no subirlo.

    `usuario` aprende de SU comportamiento; sin historia propia cae al global (cold-start).
    `detalle=True` devuelve también la evidencia por clave, para poder explicar el porqué.
    """
    import datetime
    import db
    import schema_v3
    schema_v3.migrate()
    usuario = _usuario_id(usuario)
    corte = (datetime.datetime.now() - datetime.timedelta(days=DIAS_PREF)).strftime("%Y-%m-%d %H:%M:%S")
    org, reg, tip = {}, {}, {}          # clave -> [suma_pesos, n_decisiones]
    with db.conn() as c:
        rows = []
        if usuario:
            rows = c.execute("SELECT organismo, region, tipo_producto, COALESCE(peso, 1.0) AS peso "
                             "FROM plan_feedback WHERE usuario=? AND ts >= ?",
                             (usuario, corte)).fetchall()
        if not rows:                    # sin historia del usuario aún → comportamiento global
            rows = c.execute("SELECT organismo, region, tipo_producto, COALESCE(peso, 1.0) AS peso "
                             "FROM plan_feedback WHERE ts >= ?", (corte,)).fetchall()
        for r in rows:
            p = r["peso"] if r["peso"] is not None else 1.0
            for campo, acc in (("organismo", org), ("region", reg), ("tipo_producto", tip)):
                k = r[campo]
                if k:
                    a = acc.setdefault(k, [0.0, 0])
                    a[0] += p
                    a[1] += 1

    def _pesos(d):
        if not d:
            return {}, {}
        escala = max(abs(v[0]) for v in d.values()) or 1.0
        pesos, ev = {}, {}
        for k, (suma, n) in d.items():
            confianza = n / (n + K_CONFIANZA)          # la evidencia se gana
            pesos[k] = round(PESO_PREF * (suma / escala) * confianza, 1)
            ev[k] = {"n": n, "suma": round(suma, 1), "confianza": round(confianza, 2)}
        return pesos, ev

    po, eo = _pesos(org)
    pr, er = _pesos(reg)
    pt, et = _pesos(tip)
    out = {"organismo": po, "region": pr, "tipo": pt}
    if detalle:
        out["evidencia"] = {"organismo": eo, "region": er, "tipo": et}
    return out
