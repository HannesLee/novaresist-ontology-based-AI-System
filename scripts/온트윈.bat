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
  if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" (
    start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
  ) else (
    rem 사용자 폴더 설치 등 다른 위치: 시작 메뉴에 등록된 Docker Desktop을 찾아 켠다
    powershell -NoProfile -Command "$a = Get-StartApps | Where-Object { $_.Name -like 'Docker Desktop*' } | Select-Object -First 1; if ($a) { Start-Process ('shell:AppsFolder\' + $a.AppID) } else { Write-Host '  Docker Desktop을 찾지 못했어요. 시작 메뉴에서 직접 켜 주세요.' }"
  )
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
echo   [3/3] 온트윈 켜는 중... 준비되면 온트윈 창이 열립니다(처음엔 1~3분).
start "" /min cmd /c "for /l %%i in (1,1,200) do (curl -s -o nul -m 2 http://localhost:8501/ow/ && (start msedge --app=http://localhost:8501/ow/ --window-size=1500,950 & exit) || timeout /t 3 >nul)"
wsl -e bash -lc "~/ontwin/scripts/serve.sh"
echo.
echo   온트윈이 꺼졌습니다. 아무 키나 누르면 창이 닫혀요.
pause >nul
