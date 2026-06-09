"""
main.py — orquesta el embudo y exporta a outputs/.

Embudo: para cada fecha de los últimos DIAS_HACIA_ATRAS días:
  listar -> filtrar por keyword -> dedup por código -> pedir detalle (tope
  MAX_DETALLES) -> filtrar sur -> admisibilidad + prescore -> exportar.

Exporta CSV (utf-8-sig) y JSON a outputs/candidatas_sur_AAAAMMDD_HHMM.*
Orden: admisibles primero, luego por suma de tiers ascendente.
"""
import csv
import json
import os
import sys
from datetime import datetime, timedelta

# La consola de Windows suele usar cp1252 y revienta al imprimir caracteres
# fuera de ese set (acentos raros, guiones largos, etc.). Forzar UTF-8 evita
# que main.py caiga por un nombre de licitación con un carácter inusual.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import config
from api_client import ChileCompraClient
from filters import clasificar_keywords, region_sur, admisibilidad
from prescore import prescore

OUTPUTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")

# Orden fijo de columnas para CSV/JSON (estable aunque no haya resultados).
CAMPOS = [
    "codigo", "nombre", "etiqueta", "admisible", "suma_tiers",
    "tier_logistica", "tier_cashflow", "tier_alineacion",
    "region", "region_sur", "comuna", "organismo",
    "estado", "fecha_cierre", "monto_estimado", "moneda",
    "subcontratacion", "keywords_match", "motivos_admisibilidad", "nota",
]


def fechas_recientes(dias):
    """Lista de fechas (ddmmaaaa) desde hoy hacia atrás, `dias` días."""
    hoy = datetime.now()
    return [(hoy - timedelta(days=i)).strftime("%d%m%Y") for i in range(dias)]


def _fila(codigo, det, es_admisible, motivos, ps):
    comprador = det.get("Comprador") or {}
    return {
        "codigo": codigo,
        "nombre": det.get("Nombre", ""),
        "etiqueta": ps["etiqueta"],
        "admisible": es_admisible,
        "suma_tiers": ps["suma_tiers"],
        "tier_logistica": ps["tier_logistica"],
        "tier_cashflow": ps["tier_cashflow"],
        "tier_alineacion": ps["tier_alineacion"],
        "region": comprador.get("RegionUnidad", ""),
        "region_sur": ps["region_sur"],
        "comuna": comprador.get("ComunaUnidad", ""),
        "organismo": comprador.get("NombreOrganismo", ""),
        "estado": det.get("Estado", ""),
        "fecha_cierre": det.get("FechaCierre", ""),
        "monto_estimado": det.get("MontoEstimado", ""),
        "moneda": det.get("Moneda", ""),
        "subcontratacion": det.get("SubContratacion", ""),
        "keywords_match": ", ".join(ps["keywords_match"]),
        "motivos_admisibilidad": " | ".join(motivos),
        "nota": ps["nota"],
    }


CAMPOS_DESCARTADAS = [
    "codigo", "nombre", "kw_incluir", "motivo",
    "feedback", "score_correcto_sugerido", "notas",
]


def _exportar(resultados, ts):
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    base = os.path.join(OUTPUTS_DIR, f"candidatas_sur_{ts}")
    csv_path, json_path = base + ".csv", base + ".json"

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS)
        writer.writeheader()
        writer.writerows(resultados)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)

    print(f"\nExportado: {csv_path}")
    print(f"Exportado: {json_path}")


def _exportar_descartadas(descartadas, ts):
    """Exporta las descartadas (matchearon una keyword de incluir pero se
    cayeron: por exclusión o por no ser región sur) para feedback de recall.

    La columna `feedback` queda vacía: Martin escribe `bien_descartada` o
    `falso_positivo`. `score_correcto_sugerido` y `notas` también van vacías.
    """
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    path = os.path.join(OUTPUTS_DIR, f"descartadas_{ts}.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_DESCARTADAS)
        writer.writeheader()
        for d in descartadas:
            writer.writerow({c: d.get(c, "") for c in CAMPOS_DESCARTADAS})
    print(f"Exportado: {path} ({len(descartadas)} descartadas con keyword de incluir)")


def _resumen(resultados):
    print(f"\n=== RESUMEN: {len(resultados)} candidatas del sur ===")
    if not resultados:
        print("Sin candidatas del sur en la ventana consultada.")
        return
    print("Top candidatas:")
    for r in resultados[:10]:
        adm = "ADMISIBLE  " if r["admisible"] else "INADMISIBLE"
        print(
            f"  [{r['etiqueta']:<14}] {adm} suma={r['suma_tiers']} "
            f"| {r['region_sur']:<11} | {r['codigo']} | {r['nombre'][:70]}"
        )


def main():
    print(f"Calibración cargada: {config.CALIBRACION_CARGADA}")
    print(f"Base operativa: {config.BASE_OPERATIVA}")
    if config.USANDO_TICKET_PRUEBA:
        print("Ticket: PÚBLICO DE PRUEBA (configurá LOVEO_CHILECOMPRA_TICKET en .env para producción)")
    else:
        print("Ticket: configurado desde el entorno")
    print(
        f"Ventana: últimos {config.DIAS_HACIA_ATRAS} día(s) | "
        f"tope detalles: {config.MAX_DETALLES} | delay: {config.DELAY}s\n"
    )

    client = ChileCompraClient(config.TICKET, delay=config.DELAY)

    # Descartadas: ítems que matchearon una keyword de INCLUIR pero se cayeron
    # (por exclusión o por no ser región sur). Para feedback de recall (M-1).
    descartadas = []
    descartadas_vistas = set()  # dedup por código (o nombre si no hay código)

    # 1 + 2: listar por fecha y filtrar por keyword (barato, sin detalle).
    candidatos = {}  # codigo -> nombre (dedup por código)
    for fecha in fechas_recientes(config.DIAS_HACIA_ATRAS):
        listado = client.listar_por_fecha(fecha)
        for lic in listado:
            codigo = lic.get("CodigoExterno")
            nombre = lic.get("Nombre", "")
            incluye, kw_incluir, kw_excluir = clasificar_keywords(nombre)
            if not kw_incluir:
                continue  # no matchea ninguna keyword de incluir: irrelevante
            if incluye:
                if codigo:
                    candidatos.setdefault(codigo, nombre)
            else:
                # matcheó incluir Y excluir -> se cae en el filtro de keyword
                clave = codigo or nombre
                if clave not in descartadas_vistas:
                    descartadas_vistas.add(clave)
                    descartadas.append({
                        "codigo": codigo or "",
                        "nombre": nombre,
                        "kw_incluir": ", ".join(kw_incluir),
                        "motivo": "excluida_por:" + ", ".join(kw_excluir),
                    })
        print(f"  {fecha}: {len(listado):>5} licitaciones | acumulado keyword-match: {len(candidatos)}")

    print(f"Tras keyword + dedup: {len(candidatos)} candidatas únicas")

    # 3: detalle (con tope).
    codigos = list(candidatos)[:config.MAX_DETALLES]
    if len(candidatos) > config.MAX_DETALLES:
        print(f"  Tope MAX_DETALLES={config.MAX_DETALLES}: se piden {len(codigos)} "
              f"de {len(candidatos)} (resto omitido)")

    resultados = []
    for i, codigo in enumerate(codigos, 1):
        det = client.detalle(codigo)
        if not det:
            continue
        comprador = det.get("Comprador") or {}
        region = comprador.get("RegionUnidad", "")
        # 4: filtro sur (la región solo viene en el detalle).
        if region_sur(region) is None:
            # pasó keyword pero el detalle no es región sur -> descartada (M-1)
            if codigo not in descartadas_vistas:
                descartadas_vistas.add(codigo)
                nombre = det.get("Nombre", "") or candidatos.get(codigo, "")
                _, kw_incluir, _ = clasificar_keywords(nombre)
                descartadas.append({
                    "codigo": codigo,
                    "nombre": nombre,
                    "kw_incluir": ", ".join(kw_incluir),
                    "motivo": "fuera_de_zona:" + (region or "desconocida"),
                })
            continue
        es_admisible, motivos = admisibilidad(det)
        ps = prescore(det)
        resultados.append(_fila(codigo, det, es_admisible, motivos, ps))

    # Orden: admisibles primero, luego por suma de tiers ascendente.
    resultados.sort(
        key=lambda r: (not r["admisible"], r["suma_tiers"] if r["suma_tiers"] is not None else 999)
    )

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    _exportar(resultados, ts)
    _exportar_descartadas(descartadas, ts)
    _resumen(resultados)


if __name__ == "__main__":
    main()
