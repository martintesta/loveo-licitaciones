' detener_app.vbs — cierra el proceso de streamlit que quedó corriendo en segundo plano
' (iniciar_app.vbs no deja ninguna ventana abierta para cerrar, así que se corta por puerto).

Set WshShell = CreateObject("WScript.Shell")
cmd = "powershell -NoProfile -WindowStyle Hidden -Command " & Chr(34) & _
      "Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue | " & _
      "Select-Object -ExpandProperty OwningProcess -Unique | " & _
      "ForEach-Object { Stop-Process -Id $_ -Force }" & Chr(34)
WshShell.Run cmd, 0, True

MsgBox "Loveo Licitaciones detenido.", vbInformation, "Loveo Licitaciones"
