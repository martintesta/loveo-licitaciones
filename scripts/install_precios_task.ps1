<#
install_precios_task.ps1 — Registra el REFRESCO MENSUAL DE PRECIOS como Tarea Programada de Windows.

Por que mensual y no diario: el costo es la mitad del GO/NO-GO, pero los precios de materiales no se
mueven todos los dias. Una corrida al mes mantiene el catalogo fresco sin quemar busquedas web
reconfirmando lo que ya sabiamos — `precios.py` ademas solo re-cotiza lo VENCIDO, asi que la corrida
es barata aunque el catalogo sea grande.

Cada cotizacion queda como un PUNTO NUEVO (nunca pisa el anterior) con su fecha, su hora y el LINK
de donde salio el precio. Las correcciones manuales (`python precios.py corregir ...`) no las toca.

Se registra via schtasks apuntando a scripts\tarea_precios.cmd. Dos razones:
  - schtasks soporta /SC MONTHLY nativo (New-ScheduledTaskTrigger no tiene -Monthly, y armarlo por
    CIM exige un bitmask en DaysOfMonth que es facil de romper),
  - el .cmd fija el working dir al repo, que es lo que hace falta para levantar el .env.

Uso (PowerShell, sin admin):
    powershell -ExecutionPolicy Bypass -File scripts\install_precios_task.ps1
    powershell -ExecutionPolicy Bypass -File scripts\install_precios_task.ps1 -Dia 1 -Hora 06:00
    powershell -ExecutionPolicy Bypass -File scripts\install_precios_task.ps1 -Remove

Antes de programar, proba una corrida:
    python precios.py vencidos          # que tocaria re-cotizar (no gasta nada)
    python precios.py refrescar         # la corrida real
#>
param(
    [ValidateRange(1, 28)][int]$Dia = 1,     # 1-28: el 29/30/31 no existe todos los meses
    [string]$Hora = "06:00",
    [string]$NombreTarea = "LoveoPrecios",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$Proyecto = Split-Path -Parent $PSScriptRoot
$Cmd = Join-Path $PSScriptRoot "tarea_precios.cmd"

if ($Remove) {
    # Via cmd y con los dos streams al vacio: en PS 5.1 el stderr de un .exe nativo vuelve como
    # ErrorRecord aunque se redirija con 2>$null, y borrar una tarea inexistente escupia un
    # NativeCommandError feo en vez del mensaje amable.
    cmd.exe /c ('schtasks /Delete /TN "' + $NombreTarea + '" /F >nul 2>&1')
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[ok] Tarea '$NombreTarea' eliminada."
    } else {
        Write-Host "[info] No existe una tarea '$NombreTarea' (nada que borrar)."
    }
    return
}

if (-not (Test-Path $Cmd)) {
    Write-Error "No se encontro $Cmd. Reclona el repo o restaura scripts\tarea_precios.cmd."
    return
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "No se encontro 'python' en el PATH. Instala Python o abri una consola donde 'python' funcione."
    return
}

Write-Host "Proyecto : $Proyecto"
Write-Host "Tarea    : $Cmd"
Write-Host "Horario  : el dia $Dia de cada mes a las $Hora"

# La ruta del repo tiene espacios ("AI projects"), asi que el .cmd va entre comillas DENTRO del
# valor de /TR. Se invoca por `cmd /c` a proposito: PowerShell 5.1 se come las comillas internas
# antes de que lleguen a schtasks y la tarea queda registrada con la ruta cortada en el primer
# espacio (Command=...\AI, Arguments=projects\...). Pasandole la linea armada a cmd, el quoting es
# nuestro. /F = idempotente (pisa la tarea si ya existia).
$linea = 'schtasks /Create /TN "' + $NombreTarea + '" /TR "\"' + $Cmd + '\"" /SC MONTHLY /D ' +
         $Dia + ' /ST ' + $Hora + ' /F'
cmd.exe /c $linea | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Error "schtasks no pudo registrar la tarea (codigo $LASTEXITCODE)."
    return
}

Write-Host ""
Write-Host "[ok] Tarea '$NombreTarea' registrada. Corre el dia $Dia de cada mes a las $Hora."
Write-Host "     Ejecutar ahora:  schtasks /Run /TN $NombreTarea"
Write-Host "     Ver estado:      schtasks /Query /TN $NombreTarea /FO LIST"
Write-Host "     Log:             logs\tarea_precios.log"
Write-Host "     Desinstalar:     powershell -ExecutionPolicy Bypass -File scripts\install_precios_task.ps1 -Remove"
