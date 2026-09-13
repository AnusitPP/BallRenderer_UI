@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Ball Renderer - Full Settings
if exist "C:\Users\Acer\Downloads\ffmpeg-9.0.1-essentials_build\bin\ffmpeg.exe" set "FFMPEG_EXE=C:\Users\Acer\Downloads\ffmpeg-9.0.1-essentials_build\bin\ffmpeg.exe"
set "PYTHON_EXE=C:\Users\Acer\Downloads\CircleBallRenderer_v19_WIN206_AUDIO_FIX\BallRenderer_UI\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
"%PYTHON_EXE%" "%~dp0app.py"
if errorlevel 1 pause
