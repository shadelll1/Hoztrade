@echo off
rem ===========================================================================
rem  src -> base : load the EXTENSION, update DB, check modules (asks confirmation)
rem  Settings (base path, extension name, platform): .1c-devbase.ps1
rem  Close Konfigurator and 1C:Enterprise first - training version = one session.
rem ===========================================================================
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\load.ps1" %*
set "RC=%ERRORLEVEL%"
pause
exit /b %RC%
