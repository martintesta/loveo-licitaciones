"""
api_client.py — wrapper de la API oficial de Mercado Público / ChileCompra.

Endpoint: https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json
  - Listar por fecha: ?fecha=ddmmaaaa&ticket=TICKET  -> {"Listado": [{CodigoExterno, Nombre, ...}]}
  - Detalle por código: ?codigo=CODIGO&ticket=TICKET -> {"Listado": [ {~50 campos} ]}

La API devuelve 429 si se la golpea seguido: hay backoff exponencial ante 429 y
un `delay` configurable entre llamadas exitosas. El embudo (keyword primero) es
lo que mantiene baja la cantidad de llamadas de detalle.
"""
import time

import requests

BASE_URL = "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json"


class ChileCompraClient:
    def __init__(self, ticket, delay=0.5, max_reintentos=5, timeout=30, espera_inicial=1.0):
        self.ticket = ticket
        self.delay = delay
        self.max_reintentos = max_reintentos
        self.timeout = timeout
        self.espera_inicial = espera_inicial
        self.session = requests.Session()

    def _get(self, params):
        """GET con backoff exponencial ante 429. Otros errores -> raise_for_status."""
        params = dict(params)
        params["ticket"] = self.ticket
        espera = self.espera_inicial
        for intento in range(1, self.max_reintentos + 1):
            resp = self.session.get(BASE_URL, params=params, timeout=self.timeout)
            if resp.status_code == 429:
                if intento == self.max_reintentos:
                    resp.raise_for_status()
                time.sleep(espera)
                espera *= 2
                continue
            resp.raise_for_status()
            if self.delay:
                time.sleep(self.delay)
            return resp.json()
        return None

    def listar_por_fecha(self, fecha_ddmmaaaa):
        """Lista las licitaciones publicadas en una fecha (formato ddmmaaaa)."""
        data = self._get({"fecha": fecha_ddmmaaaa})
        return (data or {}).get("Listado", []) or []

    def detalle(self, codigo):
        """Devuelve el detalle (Listado[0]) de un código, o None si no hay."""
        data = self._get({"codigo": codigo})
        listado = (data or {}).get("Listado", []) or []
        return listado[0] if listado else None
