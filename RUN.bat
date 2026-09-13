@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Ball Renderer Studio V2

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if exist "%PYTHON_EXE%" goto check_packages

set "BOOTSTRAP_PYTHON="
set "BOOTSTRAP_ARGS="
where py >nul 2>nul
if not errorlevel 1 (
    set "BOOTSTRAP_PYTHON=py"
    set "BOOTSTRAP_ARGS=-3"
)
if not defined BOOTSTRAP_PYTHON (
    where python >nul 2>nul
    if not errorlevel 1 set "BOOTSTRAP_PYTHON=python"
)
if not defined BOOTSTRAP_PYTHON goto no_python
echo Creating virtual environment...
"%BOOTSTRAP_PYTHON%" %BOOTSTRAP_ARGS% -m venv "%~dp0.venv"
if errorlevel 1 goto failed

:check_packages
"%PYTHON_EXE%" -c "import PySide6, cv2, numpy" >nul 2>nul
if not errorlevel 1 goto start
echo Installing required packages...
"%PYTHON_EXE%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto failed

:start
echo Starting Ball Renderer Studio V2...
"%PYTHON_EXE%" "%~dp0studio.py"
if errorlevel 1 goto failed
exit /b 0

:no_python
echo Python 3 was not found. Install Python 3.10 or newer.
pause
exit /b 1

:failed
echo.
echo Operation failed. Read the error above.
pause
exit /b 1
