@echo off
REM ==========================================================================
REM tarea_diaria.cmd - corrida diaria de Loveo (descubrir + score + push email)
REM run_daily.py ya llama a notificar.correr() al final: una sola tarea hace todo.
REM Portable: se ubica solo (repo = carpeta padre de \scripts). Loguea a logs\.
REM
REM Agendar (una vez, desde una consola en el repo):
REM   schtasks /Create /TN "Loveo diaria" /TR "\"%CD%\scripts\tarea_diaria.cmd\"" /SC DAILY /ST 08:00 /F
REM Quitar:   schtasks /Delete /TN "Loveo diaria" /F
REM Probar ya: schtasks /Run /TN "Loveo diaria"   (o correr este .cmd a mano)
REM ==========================================================================
setlocal
cd /d "%~dp0.."
if not exist "logs" mkdir "logs"
echo [%DATE:/=-% %TIME::=-%] inicio corrida diaria >> "logs\tarea_diaria.log"
python run_daily.py >> "logs\tarea_diaria.log" 2>&1
set "EXIT=%ERRORLEVEL%"
echo [%DATE:/=-% %TIME::=-%] fin (exit %EXIT%) >> "logs\tarea_diaria.log"
endlocal
