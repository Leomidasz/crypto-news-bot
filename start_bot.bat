@echo off
REM ดับเบิลคลิกไฟล์นี้เพื่อเปิดบอท (ต้องติดตั้งตามคู่มือก่อน)
chcp 65001 >nul
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python bot.py
pause
