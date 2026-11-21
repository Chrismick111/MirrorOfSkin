@echo off
setlocal
powershell.exe -NoProfile -STA -ExecutionPolicy RemoteSigned -File "%~dp0Workbench\import_local.ps1" -OpenWorkbench
