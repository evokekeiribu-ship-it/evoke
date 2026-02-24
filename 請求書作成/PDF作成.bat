@echo off
setlocal
chcp 65001 > nul
cd /d "%~dp0\App_Core"

echo 請求書を最新のデータからPDF化しています...
C:\Users\Owner\AppData\Local\Programs\Python\Python312\python.exe batch_gen.py
pause
