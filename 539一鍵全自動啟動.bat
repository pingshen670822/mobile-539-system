@echo off
chcp 65001 >nul
title TW539 一鍵全自動啟動 - 可視化執行中
echo.
echo ========================================
echo TW539 一鍵全自動啟動
echo 全部更新步驟會顯示在這個視窗，不再隱藏執行。
echo ========================================
echo.
set "TW539_VISIBLE_UPDATE=1"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0main_one_click.ps1"
set "TW539_EXIT=%ERRORLEVEL%"
echo.
if "%TW539_EXIT%"=="0" (
  echo TW539 全自動啟動完成。
) else (
  echo TW539 全自動啟動失敗，錯誤碼：%TW539_EXIT%
)
pause
exit /b %TW539_EXIT%
