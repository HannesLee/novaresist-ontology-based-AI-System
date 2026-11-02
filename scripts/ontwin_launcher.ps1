# 온트윈 시작 화면 (로고 + 진행 상황). 바탕화면 '온트윈' 바로가기가 실행한다.
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$url = 'http://localhost:8501/ow/'

$form = New-Object Windows.Forms.Form
$form.FormBorderStyle = 'None'; $form.StartPosition = 'CenterScreen'
$form.Size = New-Object Drawing.Size(460, 320); $form.BackColor = [Drawing.Color]::FromArgb(22, 43, 71)
$form.Text = '온트윈'; $form.ShowInTaskbar = $true; $form.TopMost = $true
try { $form.Icon = New-Object Drawing.Icon("$here\ontwin.ico") } catch {}
$pic = New-Object Windows.Forms.PictureBox
$pic.Image = [Drawing.Image]::FromFile("$here\logo.png"); $pic.SizeMode = 'Zoom'
$pic.Size = New-Object Drawing.Size(120, 120); $pic.Location = New-Object Drawing.Point(170, 36)
$title = New-Object Windows.Forms.Label
$title.Text = '온트윈 Ontwin'; $title.ForeColor = 'White'; $title.Font = New-Object Drawing.Font('Malgun Gothic', 20, [Drawing.FontStyle]::Bold)
$title.AutoSize = $false; $title.TextAlign = 'MiddleCenter'; $title.Size = New-Object Drawing.Size(460, 44); $title.Location = New-Object Drawing.Point(0, 166)
$sub = New-Object Windows.Forms.Label
$sub.Text = 'ERP + 온톨로지 + AI 업무 판단 도우미'; $sub.ForeColor = [Drawing.Color]::FromArgb(143, 182, 255); $sub.Font = New-Object Drawing.Font('Malgun Gothic', 10)
$sub.AutoSize = $false; $sub.TextAlign = 'MiddleCenter'; $sub.Size = New-Object Drawing.Size(460, 22); $sub.Location = New-Object Drawing.Point(0, 208)
$status = New-Object Windows.Forms.Label
$status.Text = '켜는 중...'; $status.ForeColor = [Drawing.Color]::FromArgb(200, 210, 230); $status.Font = New-Object Drawing.Font('Malgun Gothic', 9)
$status.AutoSize = $false; $status.TextAlign = 'MiddleCenter'; $status.Size = New-Object Drawing.Size(460, 20); $status.Location = New-Object Drawing.Point(0, 248)
$bar = New-Object Windows.Forms.ProgressBar
$bar.Style = 'Marquee'; $bar.MarqueeAnimationSpeed = 30; $bar.Size = New-Object Drawing.Size(300, 6); $bar.Location = New-Object Drawing.Point(80, 278)
$form.Controls.AddRange(@($pic, $title, $sub, $status, $bar))
$form.Show(); [Windows.Forms.Application]::DoEvents()

$logf = Join-Path $here 'launcher.log'
function Log($t) { Add-Content -Path $logf -Value ((Get-Date -Format 'HH:mm:ss') + ' ' + $t) -Encoding UTF8 }
function Step($t) { Log $t; $status.Text = $t; [Windows.Forms.Application]::DoEvents() }
function Pump($ms) { $end = (Get-Date).AddMilliseconds($ms); while ((Get-Date) -lt $end) { [Windows.Forms.Application]::DoEvents(); Start-Sleep -Milliseconds 50 } }
function OntwinUp {
  # 프록시 설정을 건너뛰고 바로 확인
  try { $r = [Net.HttpWebRequest]::Create($url); $r.Proxy = $null; $r.Timeout = 2000; $resp = $r.GetResponse(); $ok = ([int]$resp.StatusCode -eq 200); $resp.Close(); $ok } catch { $false }
}
function Wsl($cmd, [switch]$Wait) {
  # 인자를 한 줄로 넘겨야 bash -lc 가 명령 전체를 받는다
  $a = '-e bash -lc "' + $cmd + '"'
  Log "wsl $a"
  if ($Wait) { (Start-Process wsl -ArgumentList $a -WindowStyle Hidden -PassThru -Wait).ExitCode } else { Start-Process wsl -ArgumentList $a -WindowStyle Hidden | Out-Null }
}
function DockerUp { (Wsl 'docker info >/dev/null 2>&1' -Wait) -eq 0 }
function Fail($msg) { $form.TopMost = $false; [Windows.Forms.MessageBox]::Show($msg, '온트윈') | Out-Null; $form.Close(); exit 1 }

if (-not (OntwinUp)) {
  Step 'Docker 확인 중...'
  if (-not (DockerUp)) {
    Step 'Docker Desktop 켜는 중... (처음엔 1~2분)'
    if (-not (Get-Process 'Docker Desktop' -ErrorAction SilentlyContinue)) {
      $exe = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
      if (Test-Path $exe) { Start-Process $exe }
      else {
        $a = Get-StartApps | Where-Object { $_.Name -like 'Docker Desktop*' } | Select-Object -First 1
        if ($a) { Start-Process ('shell:AppsFolder\' + $a.AppID) } else { Fail 'Docker Desktop을 찾지 못했어요. 시작 메뉴에서 직접 켠 뒤 다시 실행해 주세요.' }
      }
    }
    $ok = $false
    for ($i = 0; $i -lt 120; $i++) { if (DockerUp) { $ok = $true; break }; Pump 2000 }
    if (-not $ok) { Fail 'Docker가 4분 안에 켜지지 않았어요. Docker Desktop 상태를 확인해 주세요.' }
  }
  Step 'ERPNext 켜는 중...'
  Wsl 'cd ~/frappe_docker && docker compose -f pwd.yml up -d >/dev/null 2>&1' -Wait | Out-Null
  Step '온트윈 켜는 중... (ERP 준비를 기다려요)'
  Wsl '~/ontwin/scripts/serve.sh >> ~/ontwin/ontwin.log 2>&1'
  $ok = $false
  for ($i = 0; $i -lt 150; $i++) { if (OntwinUp) { $ok = $true; break }; Pump 2000 }
  if (-not $ok) { Fail '온트윈이 켜지지 않았어요. Ubuntu에서 ~/ontwin/ontwin.log 파일을 확인해 주세요.' }
}
Step '여는 중...'
Start-Process msedge -ArgumentList "--app=$url", '--window-size=1500,950'
Pump 2500
$form.Close()
