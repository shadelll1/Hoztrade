@echo off
rem ===========================================================================
rem  base -> src : dump the EXTENSION to XML (first run full, then incremental)
rem  Settings (base path, extension name, platform): .1c-devbase.ps1
rem  Close Konfigurator and 1C:Enterprise first - training version = one session.
rem ===========================================================================
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\dump.ps1" %*
set "RC=%ERRORLEVEL%"
pause
exit /b %RC%
