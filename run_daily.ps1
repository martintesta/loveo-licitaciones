# Lanzador para la tarea programada de Windows.
# Corre el embudo (main.py) parado en la carpeta del proyecto (para que
# encuentre .env y config_local.py) y deja un log legible en logs/run.log.

Set-Location -LiteralPath $PSScriptRoot

$logDir = Join-Path $PSScriptRoot "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log = Join-Path $logDir "run.log"

# Forzar UTF-8 para que los acentos no se rompan al capturar la salida.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

# Ventana opcional: descomentá para ampliar los días que revisa.
# $env:LOVEO_DIAS_HACIA_ATRAS = "3"

$inicio = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$salida = & python main.py 2>&1 | Out-String
$code = $LASTEXITCODE
$fin = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

$bloque = "`r`n==================== $inicio  INICIO ====================`r`n" +
          $salida +
          "==================== $fin  FIN (exit $code) ===================="
Add-Content -Path $log -Value $bloque -Encoding UTF8
