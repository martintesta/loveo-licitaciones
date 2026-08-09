# DONE: precios-al-dia

> Log append-only de lo cerrado. Fecha ABSOLUTA + commit + cómo se verificó.

- 2026-08-08 `c59513b` (rama `analisis-integral-y-precios`) — Catálogo de precios vivo: refresco mensual por internet,
  correcciones manuales, historial con fecha+hora y link de origen.
  Verificado con `python scripts/preflight.py` → **413 passed, 1 skipped**.
  - `precios.py` + `tests/test_precios.py` (17 sensores, ninguno toca la red).
  - Tarea mensual registrada y **ejecutada de verdad** durante la verificación:
    `schtasks /Run /TN LoveoPreciosTEST` → `logs\tarea_precios.log` con `exit 0`.
  - Búsqueda de precios unificada: `cubicacion_ia._buscar_web_real` y el job mensual ahora cotizan
    por la misma función (`precios.buscar_precio_web`), y `analisis.precios_catalogo` delega en
    `precios.catalogo` — antes eran tres implementaciones que podían discrepar sobre "el precio
    vigente" de un material.
  - **Bug pre-existente arreglado de paso**: `install_daily_task.ps1` e `install_worker_task.ps1`
    usaban `-StopIfGoingOnBatteries:$false`, que no es un parámetro válido de
    `New-ScheduledTaskSettingsSet` (el switch es `-DontStopIfGoingOnBatteries`). Tal como estaban,
    **el registro de la tarea diaria y la del worker fallaba entero** en esta máquina. Corregidos.
  - Nota de implementación: la tarea mensual se registra por `schtasks /SC MONTHLY` invocado a
    través de `cmd /c`, no por `Register-ScheduledTask`. PowerShell 5.1 se come las comillas
    internas antes de que lleguen a schtasks y la ruta quedaba cortada en el primer espacio
    (el repo vive en `...\AI projects\...`); y el trigger mensual por CIM
    (`MSFT_TaskMonthlyTrigger`) rechaza el registro con E_INVALIDARG.
  - ⚠️ **La tarea `LoveoPrecios` NO quedó registrada.** Se verificó bajo el nombre
    `LoveoPreciosTEST` y se borró: registrar una tarea programada permanente en la máquina es
    decisión de Martín, no efecto secundario de una verificación. Para activarla:
    `powershell -ExecutionPolicy Bypass -File scripts\install_precios_task.ps1`
    (comprobar con `schtasks /Query /TN LoveoPrecios /FO LIST`). Hasta que se registre, el catálogo
    NO se refresca solo — hay que correr `python precios.py refrescar` a mano.
  - Pendiente: botón de "corregir precio" en la ficha del tablero (hoy la corrección es por CLI).
