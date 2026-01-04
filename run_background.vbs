Set WshShell = CreateObject("WScript.Shell") 
' Launch server.py using the python executable in the venv (PA)
' 0 = Hide Window
WshShell.Run "PA\Scripts\python.exe backend\server.py", 0
Set WshShell = Nothing
