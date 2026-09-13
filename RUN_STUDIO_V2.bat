@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM Use the FFmpeg build already installed on this PC, when available.
if exist "C:\Users\Acer\Downloads\ffmpeg-9.0.1-essentials_build\bin\ffmpeg.exe" set "FFMPEG_EXE=C:\Users\Acer\Downloads\ffmpeg-9.0.1-essentials_build\bin\ffmpeg.exe"

title Ball Renderer Studio V2
echo.
echo ==========================================
echo   BALL RENDERER STUDIO V2
echo ==========================================
echo.

set "PYTHON_EXE="

REM Use the existing renderer environment first. It already has PySide6 installed
REM and avoids Windows long-path failures under the .codex worktree.
if exist "C:\Users\Acer\Downloads\CircleBallRenderer_v19_WIN206_AUDIO_FIX\BallRenderer_UI\.venv\Scripts\python.exe" set "PYTHON_EXE=C:\Users\Acer\Downloads\CircleBallRenderer_v19_WIN206_AUDIO_FIX\BallRenderer_UI\.venv\Scripts\python.exe"

REM Fall back to a virtual environment inside this project.
if not defined PYTHON_EXE if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"

REM Fallback to Python Launcher, then PATH.
if not defined PYTHON_EXE (
    where py >nul 2>nul
    if not errorlevel 1 (
        echo Using Python Launcher...
        py -3 -c "import PySide6" >nul 2>nul
        if errorlevel 1 (
            echo PySide6 is missing. Install it with:
            echo py -3 -m pip install PySide6
            pause
            exit /b 1
        )
        py -3 "%~dp0studio.py"
        if errorlevel 1 exit /b 1
        exit /b 0
    )
    where python >nul 2>nul
    if not errorlevel 1 set "PYTHON_EXE=python"
)

if not defined PYTHON_EXE (
    echo Python was not found.
    echo Install Python 3.10 or newer, then run this file again.
    pause
    exit /b 1
)

"%PYTHON_EXE%" -c "import PySide6" >nul 2>nul
if errorlevel 1 (
    echo PySide6 is missing for:
    echo %PYTHON_EXE%
    echo.
    echo Install it with:
    echo "%PYTHON_EXE%" -m pip install PySide6
    pause
    exit /b 1
)

echo Starting Studio V2...
"%PYTHON_EXE%" "%~dp0studio.py"
if errorlevel 1 (
    echo.
    echo Studio V2 closed with an error.
    pause
)
