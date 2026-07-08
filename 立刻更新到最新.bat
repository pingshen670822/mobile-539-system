@echo off
chcp 65001 >nul
title TW539 立刻更新到最新 - 可視化執行中
set "CORE=%~dp0"
if not exist "%CORE%main_one_click.ps1" (
  echo 找不到主系統更新程式：%CORE%main_one_click.ps1
  pause
  exit /b 1
)
echo.
echo ========================================
echo TW539 立刻更新到最新
echo 更新過程會直接顯示在這個視窗，不再隱藏執行。
echo 跑完會自動開啟最新戰報，視窗會停住讓你確認結果。
echo ========================================
echo.
cd /d "%CORE%"
set "TW539_VISIBLE_UPDATE=1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%CORE%main_one_click.ps1"
set "TW539_EXIT=%ERRORLEVEL%"
echo.
if "%TW539_EXIT%"=="0" (
  echo TW539 更新完成，請檢查已開啟的最新戰報。
) else (
  echo TW539 更新失敗，錯誤碼：%TW539_EXIT%
)
pause
exit /b %TW539_EXIT%
