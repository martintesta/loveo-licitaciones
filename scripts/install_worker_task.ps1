<#
install_worker_task.ps1 — Registra el worker residencial como Tarea Programada de Windows.

Deja corriendo `python worker.py --once` cada N horas (solo cuando la máquina está prendida),
así no dependés de acordarte ni de dejar una consola abierta. El working directory queda fijado a
la raíz del proyecto para que worker.py levante el .env (DATABASE_URL, ticket).

Uso (PowerShell, NO hace falta admin — corre en tu usuario):
    powershell -ExecutionPolicy Bypass -File scripts\install_worker_task.ps1
    powershell -ExecutionPolicy Bypass -File scripts\install_worker_task.ps1 -IntervaloHoras 3
    powershell -ExecutionPolicy Bypass -File scripts\install_worker_task.ps1 -Remove   # desinstalar

Antes de instalar, corré el doctor:  python scripts\worker_doctor.py
#>
param(
    [int]$IntervaloHoras = 2,
    [string]$NombreTarea = "LoveoWorker",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"

# Raíz del proyecto = carpeta padre de este script.
$Proyecto = Split-Path -Parent $PSScriptRoot

if ($Remove) {
    if (Get-ScheduledTask -TaskName $NombreTarea -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $NombreTarea -Confirm:$false
        Write-Host "[ok] Tarea '$NombreTarea' eliminada."
    } else {
        Write-Host "[info] No existe una tarea '$NombreTarea'."
    }
    return
}

# Resolver el python del PATH del usuario.
$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) {
    Write-Error "No se encontró 'python' en el PATH. Instalá Python o abrí una consola donde 'python' funcione."
    return
}

Write-Host "Proyecto : $Proyecto"
Write-Host "Python   : $Python"
Write-Host "Intervalo: cada $IntervaloHoras h (mientras la máquina esté prendida)"

# Acción: python worker.py --once, con working dir en la raíz (para que cargue .env).
$Accion = New-ScheduledTaskAction -Execute $Python -Argument "worker.py --once" -WorkingDirectory $Proyecto

# Disparador: al iniciar sesión + repetición cada N horas, indefinida.
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Hours $IntervaloHoras) `
    -RepetitionDuration ([TimeSpan]::MaxValue)).Repetition

# Correr en tu sesión, sin admin. AllowStartIfOnBatteries + StopIfGoingOnBatteries:$false para que
# una descarga en curso NO se corte si el notebook pasa a batería (dejaría bases a medias).
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries -StopIfGoingOnBatteries:$false -MultipleInstances IgnoreNew

if (Get-ScheduledTask -TaskName $NombreTarea -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $NombreTarea -Confirm:$false   # idempotente: re-registra limpio
}

Register-ScheduledTask -TaskName $NombreTarea -Action $Accion -Trigger $Trigger `
    -Settings $Settings -Description "Loveo: worker residencial Capa B+C (worker.py --once)" | Out-Null

Write-Host ""
Write-Host "[ok] Tarea '$NombreTarea' registrada. Corre al iniciar sesión y cada $IntervaloHoras h."
Write-Host "     Ver/ejecutar ahora:  Start-ScheduledTask -TaskName $NombreTarea"
Write-Host "     Ver estado:          Get-ScheduledTask -TaskName $NombreTarea | Get-ScheduledTaskInfo"
Write-Host "     Desinstalar:         powershell -ExecutionPolicy Bypass -File scripts\install_worker_task.ps1 -Remove"
