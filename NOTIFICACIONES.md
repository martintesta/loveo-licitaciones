# Avisos de deadline (email)

`notificar.py` manda un **email digest** cuando una licitación **en juego** entra en la ventana de
alerta: cierre o visita a terreno a `LOVEO_DIAS_ALERTA` días o menos (default 5). Cierra M-2 — el
tablero ya mostraba los deadlines, ahora los **empuja** para que no se pasen por no abrir la app.

- Solo licitaciones activas (no descartadas, no presentadas/cerradas).
- **Un aviso por evento** (cierre y visita se avisan por separado).
- **Dedup**: cada `(código, tipo, fecha)` se avisa una sola vez. Si el organismo mueve el deadline,
  se vuelve a avisar. Sin spam: si no hay nada nuevo, no manda mail.

## Configuración (env / `.env`) — nada hardcodeado

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587                 # opcional, default 587 (STARTTLS)
SMTP_USER=tu-cuenta@gmail.com
SMTP_PASS=app-password        # NO tu password normal: usá una "app password"
SMTP_FROM=tu-cuenta@gmail.com # opcional, default = SMTP_USER
LOVEO_ALERT_TO=valentina@loveo.cl, martin@loveo.cl   # coma-separado
```

Sin `SMTP_HOST` o sin `LOVEO_ALERT_TO`, `notificar.correr()` **degrada a no-op** (no falla): calcula
a quién avisaría pero no envía.

## Cómo corre

Ya está enganchado al **pipeline diario**: `run_daily.py` lo llama al final, así que si programás
el run diario (cron / Task Scheduler), los avisos salen solos. Un fallo de email nunca frena el run.

Manual / prueba:
```bash
python notificar.py --dry     # muestra a quién avisaría, SIN enviar ni registrar
python notificar.py           # una pasada real (manda + registra)
```

## Futuro (no v1)

- Recordatorio a T-1 además del primer aviso (hoy avisa una vez al entrar en ventana).
- Canal WhatsApp además de email.
