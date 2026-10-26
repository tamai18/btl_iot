@echo off
chcp 65001 >nul
title Gia lap ESP32 ao nuoi - MQTT Tester

echo ================================================
echo  BO GIA LAP ESP32 + HC-SR04 + RELAY (BUOC 3)
echo  Gui du lieu muc nuoc, nhan lenh dieu khien MQTT
echo ================================================
echo.

cd backend
python esp32_simulator.py

if %errorlevel% neq 0 (
    echo.
    echo [THONG BAO] Gia lap dung hoac gap loi ket noi MQTT.
    echo Hay kiem tra xem Mosquitto broker da duoc bat chua.
)

pause
