@echo off
cd /d "%~dp0.."
python -m streamlit run tablero3.py --server.port 8502 --server.headless true
