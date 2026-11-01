@echo off
rem 창을 작업 표시줄로 내린 채 다시 실행
if not "%~1"=="min" (
  start "" /min "%~f0" min
  exit /b
)
chcp 65001 >nul
title 온트윈 Ontwin
echo.
echo   ◐ 온트윈을 켜는 중입니다. 이 창을 닫으면 온트윈이 꺼져요.
echo.
tasklist /fi "imagename eq Docker Desktop.exe" | find /i "Docker Desktop.exe" >nul
if errorlevel 1 (
  echo   [1/3] Docker Desktop 켜는 중...
  start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
)
echo   [1/3] Docker 준비 기다리는 중...
:waitdocker
wsl -e bash -lc "docker info >/dev/null 2>&1"
if errorlevel 1 (
  timeout /t 3 >nul
  goto waitdocker
)
echo   [2/3] ERPNext 켜는 중...
wsl -e bash -lc "cd ~/frappe_docker && docker compose -f pwd.yml up -d >/dev/null 2>&1"
echo   [3/3] 온트윈 켜는 중... 잠시 뒤 온트윈 창이 열립니다.
start "" /min cmd /c "timeout /t 12 >nul & start "" msedge --app=http://localhost:8501/ow/ --window-size=1500,950"
wsl -e bash -lc "~/ontwin/scripts/serve.sh"
echo.
echo   온트윈이 꺼졌습니다. 아무 키나 누르면 창이 닫혀요.
pause >nul
