@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" app.py
    exit /b %errorlevel%
)

if exist "%~dp0..\circle_line_battle_240fps\.venv\Scripts\python.exe" (
    "%~dp0..\circle_line_battle_240fps\.venv\Scripts\python.exe" app.py
    exit /b %errorlevel%
)

where py >nul 2>nul
if not errorlevel 1 (
    py -3 app.py
    exit /b %errorlevel%
)

where python >nul 2>nul
if not errorlevel 1 (
    python app.py
    exit /b %errorlevel%
)

echo Python was not found. Run START_HERE.bat first.
pause
