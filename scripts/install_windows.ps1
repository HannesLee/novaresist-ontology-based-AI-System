# 온트윈 바탕화면 바로가기 설치 (한 번만 실행)
$src = Split-Path -Parent $MyInvocation.MyCommand.Path
$dst = Join-Path $env:LOCALAPPDATA 'Ontwin'
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item "$src\ontwin_launcher.ps1", "$src\ontwin.vbs", "$src\ontwin.ico" -Destination $dst -Force
Copy-Item "$src\..\app\web\static\img\logo.png" -Destination $dst -Force
$desk = [Environment]::GetFolderPath('Desktop')
$sh = New-Object -ComObject WScript.Shell
$lnk = $sh.CreateShortcut((Join-Path $desk '온트윈.lnk'))
$lnk.TargetPath = "$env:WINDIR\System32\wscript.exe"
$lnk.Arguments = '"' + (Join-Path $dst 'ontwin.vbs') + '"'
$lnk.IconLocation = (Join-Path $dst 'ontwin.ico') + ',0'
$lnk.WorkingDirectory = $dst
$lnk.Description = '온트윈 Ontwin'
$lnk.Save()
$old = Join-Path $desk '온트윈.bat'
if (Test-Path $old) { Remove-Item $old -Force }
Write-Host '바탕화면에 온트윈 바로가기를 만들었어요.'
