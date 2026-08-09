<#
install_daily_task.ps1 — Registra el RUN DIARIO (discovery + admisibilidad + scoring + avisos) como
Tarea Programada de Windows. Es el que mantiene el embudo fresco y dispara los avisos de deadline.

A diferencia del worker (Capa B, IP residencial), el run diario es Capa A: corre desde cualquier
red (la API responde). Fija el working dir al proyecto para levantar el .env (ticket, DATABASE_URL,
SMTP para los avisos).

Uso (PowerShell, sin admin):
    powershell -ExecutionPolicy Bypass -File scripts\install_daily_task.ps1
    powershell -ExecutionPolicy Bypass -File scripts\install_daily_task.ps1 -Hora 07:30
    powershell -ExecutionPolicy Bypass -File scripts\install_daily_task.ps1 -Remove   # desinstalar

Antes de programar, probá una corrida:  python run_daily.py
#>
param(
    [string]$Hora = "08:00",
    [string]$NombreTarea = "LoveoDaily",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
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

$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) {
    Write-Error "No se encontró 'python' en el PATH. Instalá Python o abrí una consola donde 'python' funcione."
    return
}

Write-Host "Proyecto : $Proyecto"
Write-Host "Python   : $Python"
Write-Host "Horario  : todos los días a las $Hora"

# Acción: python run_daily.py (sin args = hoy), con working dir en la raíz (para cargar .env).
$Accion = New-ScheduledTaskAction -Execute $Python -Argument "run_daily.py" -WorkingDirectory $Proyecto

# Disparador diario a la hora indicada.
$Trigger = New-ScheduledTaskTrigger -Daily -At $Hora

# Si la máquina estaba apagada a esa hora, correr cuando vuelva; correr con o sin batería.
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew

if (Get-ScheduledTask -TaskName $NombreTarea -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $NombreTarea -Confirm:$false   # idempotente
}

Register-ScheduledTask -TaskName $NombreTarea -Action $Accion -Trigger $Trigger `
    -Settings $Settings -Description "Loveo: run diario (discovery + scoring + avisos de deadline)" | Out-Null

Write-Host ""
Write-Host "[ok] Tarea '$NombreTarea' registrada. Corre todos los días a las $Hora."
Write-Host "     Ejecutar ahora:  Start-ScheduledTask -TaskName $NombreTarea"
Write-Host "     Ver estado:      Get-ScheduledTask -TaskName $NombreTarea | Get-ScheduledTaskInfo"
Write-Host "     Desinstalar:     powershell -ExecutionPolicy Bypass -File scripts\install_daily_task.ps1 -Remove"
