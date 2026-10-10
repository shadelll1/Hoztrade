@echo off
rem Сайт в режиме разработки: http://localhost:8000
cd /d "%~dp0"
.venv\Scripts\python.exe manage.py runserver 8000
