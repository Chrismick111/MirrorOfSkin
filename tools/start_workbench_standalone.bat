@echo off
setlocal DisableDelayedExpansion
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0start_workbench_standalone.ps1" "%~1"
set "result=%errorlevel%"
if not "%result%"=="0" pause
exit /b %result%
