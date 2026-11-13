Set WshShell = CreateObject("WScript.Shell")
Set Fso = CreateObject("Scripting.FileSystemObject")
Carpeta = Fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = Carpeta
WshShell.Run """" & Carpeta & "\.venv\Scripts\python.exe"" main.py", 0, False
