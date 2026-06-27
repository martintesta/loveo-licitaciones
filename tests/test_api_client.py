"""
test_api_client.py — Integración del cliente ChileCompra con el HTTP mockeado.

No toca la red: reemplaza session.get por respuestas canned y verifica el armado de params
(ticket), el parseo de Listado, la detección del error "Mensaje" (200 sin Listado) y el retry 429.

  python -m pytest tests/test_api_client.py -q
"""
import pytest

import api_client


class _Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _make(monkeypatch, responses):
    c = api_client.ChileCompraClient("TICKET-X", delay=0, espera_inicial=0)
    it = iter(responses)
    cap = {}

    def fake_get(url, params=None, timeout=None):
        cap["params"] = params
        return next(it)

    monkeypatch.setattr(c.session, "get", fake_get)
    monkeypatch.setattr(api_client.time, "sleep", lambda *a, **k: None)
    return c, cap


def test_listar_parsea_y_agrega_ticket(monkeypatch):
    c, cap = _make(monkeypatch, [_Resp(200, {"Listado": [{"CodigoExterno": "1"}]})])
    assert c.listar_por_fecha("11062026") == [{"CodigoExterno": "1"}]
    assert cap["params"]["ticket"] == "TICKET-X"
    assert cap["params"]["fecha"] == "11062026"


def test_detalle_primero_o_none(monkeypatch):
    c, _ = _make(monkeypatch, [_Resp(200, {"Listado": [{"a": 1}, {"a": 2}]})])
    assert c.detalle("X")["a"] == 1
    c2, _ = _make(monkeypatch, [_Resp(200, {"Listado": []})])
    assert c2.detalle("X") is None


def test_mensaje_de_error_levanta(monkeypatch):
    # La API responde 200 con {Codigo, Mensaje} y SIN Listado ante "Ticket no válido".
    c, _ = _make(monkeypatch, [_Resp(200, {"Codigo": 9, "Mensaje": "Ticket no valido"})])
    with pytest.raises(RuntimeError):
        c.listar_por_fecha("11062026")


def test_429_reintenta_y_recupera(monkeypatch):
    c, _ = _make(monkeypatch, [_Resp(429), _Resp(200, {"Listado": [{"x": 1}]})])
    assert c.listar_por_fecha("11062026") == [{"x": 1}]
