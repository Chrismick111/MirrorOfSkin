@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoProfile -STA -ExecutionPolicy RemoteSigned -File "%~dp0Workbench\import_local.ps1" %*
set "skin_status=%ERRORLEVEL%"
pause
exit /b %skin_status%
