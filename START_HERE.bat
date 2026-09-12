@echo off
setlocal
cd /d "%~dp0"
echo Starting Ball Renderer setup...
call build_exe.bat
if errorlevel 1 exit /b 1
echo.
echo Opening the built app folder...
start "" "%~dp0dist"
