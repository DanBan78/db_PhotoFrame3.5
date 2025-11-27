@echo off
REM PhotoFrame - Start without console window
REM Uses pythonw.exe to run in background without CMD window

cd /d "%~dp0"
pythonw.exe main.py
