@echo off
setlocal
cd /d "%~dp0"
echo Sensor-detect is running at http://[::1]:8000
echo Press Ctrl+C to stop.
python backend\app\main.py
