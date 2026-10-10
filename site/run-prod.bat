@echo off
rem Сайт в боевом режиме (DEBUG=False, waitress): http://localhost:8000
cd /d "%~dp0"
set DEBUG=False
.venv\Scripts\python.exe manage.py collectstatic --noinput
.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:8000 config.wsgi:application
