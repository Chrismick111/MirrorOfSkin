@echo off
chcp 65001 >nul
setlocal

REM One-click standalone Mirror of Skin workbench backend.
REM Real backend, not a static preview. The process stays alive.

set "ROOT=%~dp0.."
set "ADDON=D:\FaustLauncher\addons\faust_inst_uplabl34"
if not exist "%ADDON%\addon_info.json" set "ADDON=%ROOT%\MirrorOfSkin"

set "WB=%ADDON%\Workbench\workbench.py"
if not exist "%WB%" set "WB=%ROOT%\MirrorOfSkin\Workbench\workbench.py"

set "PY="
for %%P in (
  "D:\FaustLauncher\resources\mod_loader\_internal\venv\Bins\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
) do if exist %%~P (
  set "PY=%%~P"
  goto :found_python
)
where python >nul 2>nul && (
  set "PY=python"
  goto :found_python
)

echo [ERROR] No Python interpreter found.
pause
exit /b 1

:found_python
echo Addon : %ADDON%
echo Script: %WB%
echo Python: %PY%
echo.
echo Starting standalone workbench backend. Browser will open automatically.
start "MOS Workbench" "%PY%" "%WB%" --addon "%ADDON%"
echo.
echo Started. Stop it by closing the "MOS Workbench" window
echo or ending the matching python.exe process in Task Manager.
ping -n 4 127.0.0.1 >nul
endlocal
