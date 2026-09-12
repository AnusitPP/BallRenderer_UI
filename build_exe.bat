@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo === Ball Renderer EXE Builder ===
echo.

set "PYTHON_EXE="
set "PYTHON_ARGS="

REM 1) Local .venv
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
)

REM 2) Existing renderer venv next to Downloads project
if not defined PYTHON_EXE if exist "%~dp0..\circle_line_battle_240fps\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0..\circle_line_battle_240fps\.venv\Scripts\python.exe"
)

REM 3) Search other .venv folders under Downloads
if not defined PYTHON_EXE if defined USERPROFILE (
    for /d %%D in ("%USERPROFILE%\Downloads\*") do (
        if not defined PYTHON_EXE if exist "%%~fD\.venv\Scripts\python.exe" (
            set "PYTHON_EXE=%%~fD\.venv\Scripts\python.exe"
        )
    )
)

REM 4) Windows Python Launcher
if not defined PYTHON_EXE (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 --version >nul 2>nul
        if not errorlevel 1 (
            set "PYTHON_EXE=py"
            set "PYTHON_ARGS=-3"
        )
    )
)

REM 5) Python from PATH
if not defined PYTHON_EXE (
    where python >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_EXE=python"
    )
)

if not defined PYTHON_EXE (
    echo.
    echo Python was not found.
    echo Checked local .venv, your old renderer .venv, Downloads .venv folders, py -3 and PATH.
    echo.
    pause
    exit /b 1
)

echo Python found:
echo %PYTHON_EXE%
echo.

REM Create a local virtual environment so future builds are independent.
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Creating local .venv...
    "%PYTHON_EXE%" %PYTHON_ARGS% -m venv "%~dp0.venv"
    if errorlevel 1 (
        echo Failed to create local .venv.
        pause
        exit /b 1
    )
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
    set "PYTHON_ARGS="
)

echo Checking Python...
"%PYTHON_EXE%" %PYTHON_ARGS% --version
if errorlevel 1 (
    echo Python was found but could not be started.
    pause
    exit /b 1
)

echo.
echo Installing requirements...
"%PYTHON_EXE%" %PYTHON_ARGS% -m pip install --upgrade pip
if errorlevel 1 (
    echo Failed to upgrade pip.
    pause
    exit /b 1
)

"%PYTHON_EXE%" %PYTHON_ARGS% -m pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install requirements.
    pause
    exit /b 1
)

echo.
echo Building BallRenderer.exe...
"%PYTHON_EXE%" %PYTHON_ARGS% -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name BallRenderer ^
  app.py

if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Preparing external melody and output folders...
if exist "%~dp0dist\melodies" rmdir /s /q "%~dp0dist\melodies"
mkdir "%~dp0dist\melodies" >nul 2>nul
xcopy "%~dp0melodies\*" "%~dp0dist\melodies\" /E /I /Y >nul
if exist "%~dp0dist\patterns" rmdir /s /q "%~dp0dist\patterns"
mkdir "%~dp0dist\patterns" >nul 2>nul
xcopy "%~dp0patterns\*" "%~dp0dist\patterns\" /E /I /Y >nul

if not exist "%~dp0dist\output" mkdir "%~dp0dist\output"

echo.
echo ==========================================
echo Build complete
echo ==========================================
echo.
echo EXE:
echo %~dp0dist\BallRenderer.exe
echo.
echo Melody folder:
echo %~dp0dist\melodies
echo.
echo You can add JSON or MIDI files to that melodies folder later.
echo No EXE rebuild is required for new melody files.
echo.
pause

if exist "assets\balls" xcopy /E /I /Y "assets\balls" "dist\assets\balls" >nul
