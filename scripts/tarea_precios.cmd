@echo off
REM ==========================================================================
REM tarea_precios.cmd - refresco MENSUAL del catalogo de precios.
REM
REM Re-cotiza por internet solo los materiales VENCIDOS y guarda cada resultado
REM como un PUNTO NUEVO (nunca pisa el anterior) con su fecha, su hora y el LINK
REM de donde salio el precio. Las correcciones manuales no las toca.
REM
REM Portable: se ubica solo (repo = carpeta padre de \scripts) y fija el working
REM dir, que es lo que hace falta para levantar el .env (ANTHROPIC_API_KEY,
REM DATABASE_URL). Loguea a logs\.
REM
REM Agendar (una vez):  powershell -ExecutionPolicy Bypass -File scripts\install_precios_task.ps1
REM Probar a mano:      scripts\tarea_precios.cmd
REM Ver que tocaria:    python precios.py vencidos
REM ==========================================================================
setlocal
cd /d "%~dp0.."
if not exist "logs" mkdir "logs"
echo [%DATE:/=-% %TIME::=-%] inicio refresco de precios >> "logs\tarea_precios.log"
python precios.py refrescar >> "logs\tarea_precios.log" 2>&1
set "EXIT=%ERRORLEVEL%"
echo [%DATE:/=-% %TIME::=-%] fin (exit %EXIT%) >> "logs\tarea_precios.log"
endlocal
