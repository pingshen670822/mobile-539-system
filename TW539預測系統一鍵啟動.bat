@echo off
chcp 65001 >nul
title TW539 預測系統一鍵啟動 - 可視化執行中
set "CORE=%~dp0"
if not exist "%CORE%main_one_click.ps1" (
  echo 找不到主系統更新程式：%CORE%main_one_click.ps1
  pause
  exit /b 1
)
echo.
echo ========================================
echo TW539 預測系統一鍵啟動
echo 更新、重算、戰報、手機同步都會顯示在這個視窗。
echo ========================================
echo.
cd /d "%CORE%"
set "TW539_VISIBLE_UPDATE=1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%CORE%main_one_click.ps1"
set "TW539_EXIT=%ERRORLEVEL%"
echo.
if "%TW539_EXIT%"=="0" (
  echo TW539 一鍵啟動完成。
) else (
  echo TW539 一鍵啟動失敗，錯誤碼：%TW539_EXIT%
)
pause
exit /b %TW539_EXIT%
