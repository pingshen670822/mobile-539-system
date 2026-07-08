@echo off
chcp 65001 >nul
title TW539 visible full update
echo.
echo ========================================
echo TW539 visible full update
echo All update steps will be printed in this window.
echo ========================================
echo.
set "TW539_VISIBLE_UPDATE=1"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0main_one_click.ps1"
set "TW539_EXIT=%ERRORLEVEL%"
echo.
if "%TW539_EXIT%"=="0" (
  echo TW539 update completed.
) else (
  echo TW539 update failed. Exit code: %TW539_EXIT%
)
pause
exit /b %TW539_EXIT%
