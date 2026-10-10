@echo off
rem Сайт в боевом режиме (DEBUG=False, waitress): http://localhost:8000. Другой порт — первым аргументом.
cd /d "%~dp0"
set DEBUG=False
set PORT=%~1
if "%PORT%"=="" set PORT=8000
.venv\Scripts\python.exe manage.py migrate --noinput || exit /b 1
.venv\Scripts\python.exe manage.py collectstatic --noinput || exit /b 1
.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:%PORT% --threads=8 config.wsgi:application
