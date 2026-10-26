@echo off
setlocal
chcp 65001 >nul
title Khoi dong he thong ao nuoi IoT

cd /d "%~dp0"

echo ================================================
echo  HE THONG GIAM SAT MUC NUOC AO NUOI
echo  ESP32 + HC-SR04 + MQTT + Flask + MySQL
echo ================================================
echo.

echo [1/3] Kiem tra Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Python chua duoc cai dat hoac chua co trong PATH.
    echo       Tai tai: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] Cai/kiem tra thu vien Python...
python -m pip install -r "%~dp0backend\requirements.txt" -q
if errorlevel 1 (
    echo [LOI] Khong the cai thu vien Python.
    echo       Thu chay: python -m pip install -r backend\requirements.txt
    pause
    exit /b 1
)
echo [OK] Thu vien san sang.

if not exist "%~dp0backend\.env" (
    echo [2/3] Tao file backend\.env tu .env.example...
    copy /y "%~dp0backend\.env.example" "%~dp0backend\.env" >nul
    if errorlevel 1 (
        echo [LOI] Khong tao duoc file backend\.env.
        pause
        exit /b 1
    )
    echo [CHU Y] Hay kiem tra/cap nhat backend\.env neu dung MySQL hoac MQTT rieng.
    echo.
    notepad "%~dp0backend\.env"
) else (
    echo [2/3] File backend\.env da ton tai.
)

echo [3/3] Khoi dong Flask backend...
echo.
echo  Website: http://localhost:5000
echo  API:     http://localhost:5000/api/status
echo.
echo  Nhan Ctrl+C de dung
echo ================================================
echo.

cd /d "%~dp0backend"
python app.py

set "APP_EXIT=%errorlevel%"
echo.
echo Backend da dung voi ma loi %APP_EXIT%.
pause
exit /b %APP_EXIT%
