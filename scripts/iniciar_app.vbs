' iniciar_app.vbs — abre Loveo Licitaciones sin ventana de consola (estilo app on-premise).
' Doble clic: levanta streamlit en segundo plano (oculto) y abre el navegador en localhost:8501.
' Para cerrar la app, usar detener_app.vbs (streamlit sigue corriendo en segundo plano si solo
' se cierra la pestaña del navegador).

Set WshShell = CreateObject("WScript.Shell")
repoDir = "C:\Users\marti\OneDrive\Escritorio\Desktop\AI projects\loveo-licitaciones"

WshShell.Run "cmd /c cd /d """ & repoDir & """ && python -m streamlit run tablero3.py", 0, False

WScript.Sleep 4000
WshShell.Run "http://localhost:8501", 1, False
