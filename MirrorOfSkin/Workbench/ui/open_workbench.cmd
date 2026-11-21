@echo off
setlocal
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0open_workbench.ps1" %*
if errorlevel 1 (
  echo.
  echo Workbench failed to start. See %TEMP%\FaustRandomIdentity-Workbench
  pause
)
