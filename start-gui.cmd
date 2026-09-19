@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "%~dp0FunSportWorld.pyw"
    exit /b
)
where pythonw >nul 2>nul
if not errorlevel 1 (
    start "" pythonw "%~dp0FunSportWorld.pyw"
    exit /b
)
where pyw >nul 2>nul
if not errorlevel 1 (
    start "" pyw -3 "%~dp0FunSportWorld.pyw"
    exit /b
)
echo Python with Tkinter is required. Install Python 3.8+ and requirements.txt.
pause
exit /b 1
