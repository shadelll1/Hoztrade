@echo off
rem ===========================================================================
rem  base -> base-src : dump the MAIN BP configuration, read-only reference (slow)
rem  Settings (base path, extension name, platform): .1c-devbase.ps1
rem  Close Konfigurator and 1C:Enterprise first - training version = one session.
rem ===========================================================================
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\dump-base.ps1" %*
set "RC=%ERRORLEVEL%"
pause
exit /b %RC%
