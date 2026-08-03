@echo off
REM ==========================================================================
REM levantar_app.cmd - arranca el tablero Loveo en local y abre el navegador.
REM Doble-click (o el acceso directo del escritorio) lo levanta en :8502.
REM Cerrá esta ventana para apagar el servidor.
REM Portable: se ubica solo (repo = carpeta padre de \scripts).
REM ==========================================================================
title Loveo Licitaciones - servidor local (NO cerrar mientras uses la app)
cd /d "%~dp0.."
echo Levantando el tablero Loveo en http://localhost:8502 ...
echo (se abre el navegador solo; cerra esta ventana para apagar el servidor)
python -m streamlit run tablero3.py --server.port 8502 --server.headless false
pause
