@echo off
setlocal
cd /d "%~dp0"
set SENSOR_DETECT_MODE=github
set SENSOR_DETECT_MODEL=chuangchuangtan/NPR-DeepfakeDetection
set SENSOR_DETECT_WEIGHTS=%~dp0backend\models\NPR.pth
echo Sensor-detect is running at http://[::1]:8000
echo GitHub model: %SENSOR_DETECT_MODEL%
echo Weights: %SENSOR_DETECT_WEIGHTS%
echo Press Ctrl+C to stop.
python backend\app\main.py
