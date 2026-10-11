@echo off
chcp 65001 >nul
rem Сайт в интернете с этого компьютера: боевой режим с настройками из .env.public (домен, HTTPS, почта)
rem на 127.0.0.1:8000. Снаружи его открывает Caddy - deploy\windows\run-caddy.bat.
cd /d "%~dp0"
if not exist .env.public (echo Нет .env.public - скопировать из .env.public.example & exit /b 1)
set ENV_FILE=.env.public
call run-prod.bat 8000
