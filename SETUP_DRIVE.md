# Conectar Google Drive (una sola vez)

Para que el sistema entre a una carpeta de Drive y lea todos los documentos, necesita una
credencial de la **API de Google Drive**. Es de **solo lectura**. Elegí UNA de las dos vías.

---

## Opción A — OAuth con tu cuenta (recomendada)
Accede a **toda tu Drive** con tu consentimiento; no hace falta compartir cada carpeta.

1. Entrá a https://console.cloud.google.com/ y creá un proyecto (o usá uno) — botón "Proyecto nuevo".
2. **Habilitá la API**: buscador → "Google Drive API" → **Habilitar**.
3. **Pantalla de consentimiento OAuth**: menú "APIs y servicios" → "Pantalla de consentimiento OAuth" →
   tipo **Externo** → completá nombre de la app y tu email → en **Usuarios de prueba** agregá tu propio email.
4. **Credenciales**: "APIs y servicios" → "Credenciales" → "Crear credenciales" → **ID de cliente de OAuth** →
   tipo de aplicación **App de escritorio** → Crear → **Descargar JSON**.
5. Guardá ese archivo como **`credentials.json`** en la carpeta del proyecto (`loveo-licitaciones/`).
6. Corré una vez:  `python drive.py auth`  → se abre el navegador, das permiso, y se genera `token.json`.

Listo. (Si el token caduca, se renueva solo; si no, repetís el paso 6.)

---

## Opción B — Cuenta de servicio (alternativa)
No abre navegador, pero tenés que **compartir cada carpeta** con el email del servicio.

1. Pasos 1 y 2 de arriba (proyecto + habilitar Drive API).
2. "Credenciales" → "Crear credenciales" → **Cuenta de servicio** → creala.
3. En la cuenta de servicio → pestaña "Claves" → "Agregar clave" → **JSON** → descargá.
4. Guardalo como **`service_account.json`** en la carpeta del proyecto.
5. En Drive, **compartí la carpeta** del proyecto con el email de la cuenta de servicio
   (`...@...iam.gserviceaccount.com`), como **Lector**.

---

## Probar
```bash
python drive.py ls  "https://drive.google.com/drive/folders/XXXX"   # lista los archivos
python drive.py get "https://drive.google.com/drive/folders/XXXX" storage/PRUEBA   # baja todo
```

## Seguridad
`credentials.json`, `token.json` y `service_account.json` están en `.gitignore` — **nunca se suben**.
El acceso es `drive.readonly` (solo lectura).
