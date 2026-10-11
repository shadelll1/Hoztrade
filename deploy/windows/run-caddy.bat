@echo off
chcp 65001 >nul
rem HTTPS-прокси для сайта в интернете с этого компьютера. Caddy: caddy.exe рядом с этим файлом (docs/deploy.md).
rem Настройки (домен, папка фото) - из site\.env.public. Сертификаты Caddy хранит в %AppData%\Caddy.
cd /d "%~dp0"
if not exist caddy.exe (echo Нет caddy.exe в %~dp0 & exit /b 1)
if not exist ..\..\site\.env.public (echo Нет site\.env.public - скопировать из .env.public.example & exit /b 1)
caddy.exe run --config Caddyfile --adapter caddyfile --envfile ..\..\site\.env.public
