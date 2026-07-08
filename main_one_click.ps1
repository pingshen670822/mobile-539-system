param(
  [switch]$NoOpen
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $ScriptDir "logs"
$ReportDir = Join-Path $ScriptDir "reports"
$StatusPath = Join-Path $ReportDir "one_click_status.json"
$RunLog = Join-Path $LogDir ("one_click_run_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")
$ScheduleRepairName = (-join ([char[]](0x6BCF,0x65E5,0x81EA,0x52D5,0x66F4,0x65B0,0x6392,0x7A0B,0x4FEE,0x5FA9))) + ".ps1"
$ScheduleRepairPath = Join-Path $ScriptDir $ScheduleRepairName

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null

function Write-RunLog {
  param([string]$Message)
  $line = (Get-Date -Format "s") + " " + $Message
  Write-Host $line
  Add-Content -LiteralPath $RunLog -Value $line -Encoding UTF8
}

function Write-OneClickStatus {
  param(
    [string]$Status,
    [string]$Step,
    [string]$Message
  )
  $visibleUpdate = $false
  if ($env:TW539_VISIBLE_UPDATE -eq "1") {
    $visibleUpdate = $true
  }
  $payload = @{
    status = $Status
    step = $Step
    message = $Message
    written_at = (Get-Date -Format "s")
    log = $RunLog
    visible_update = $visibleUpdate
    core_path = $ScriptDir
    report_path = (Join-Path $ReportDir "latest_battle_report.html")
  }
  $payload | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $StatusPath -Encoding UTF8
}

function Resolve-Python {
  $candidates = @(
    (Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"),
    "python.exe",
    "python"
  )
  foreach ($candidate in $candidates) {
    try {
      $command = Get-Command $candidate -ErrorAction Stop
      if ($command.Source) {
        return $command.Source
      }
    } catch {
    }
  }
  throw "Python runtime was not found."
}

function Invoke-LoggedCommand {
  param(
    [string]$Step,
    [scriptblock]$Command
  )
  Write-RunLog ("START " + $Step)
  Write-OneClickStatus "running" $Step "Step is running."
  try {
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $global:LASTEXITCODE = 0
    & $Command 2>&1 | ForEach-Object {
      $text = $_.ToString()
      Write-Host $text
      Add-Content -LiteralPath $RunLog -Value $text -Encoding UTF8
    }
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    if ($exitCode -ne $null -and $exitCode -ne 0) {
      throw ("Step exited with code " + $exitCode)
    }
    Write-RunLog ("PASS " + $Step)
  } catch {
    $ErrorActionPreference = "Stop"
    Write-RunLog ("FAIL " + $Step + " : " + $_.Exception.Message)
    Write-OneClickStatus "failed" $Step $_.Exception.Message
    throw
  }
}

Set-Location -LiteralPath $ScriptDir
$Python = Resolve-Python
Write-OneClickStatus "running" "start" "TW539 visible one-click update started."
Write-Host ""
Write-Host "========================================"
Write-Host "TW539 update is running visibly in this window."
Write-Host "Every step will be printed here and saved to the status file."
Write-Host "========================================"
Write-Host ""
Write-RunLog "TW539 one click full run started."
Write-RunLog ("Python=" + $Python)

Invoke-LoggedCommand "compile check" {
  & $Python -m py_compile ".\update_539.py" ".\analyze_539.py" ".\industrial_engine.py" ".\stability_governor.py" ".\battle_report.py" ".\pages_build.py" ".\verify_mobile_sync.py" ".\daily_integrity_audit.py" ".\system_file_check.py"
}

Invoke-LoggedCommand "daily automatic schedule repair" {
  & "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File $ScheduleRepairPath
}

Invoke-LoggedCommand "latest draw update and full rebuild" {
  & $Python ".\update_539.py" "--latest" "--require-fresh" "--retry-until-fresh-minutes" "20"
}

Invoke-LoggedCommand "mobile cloud publish" {
  & "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File ".\publish_free_github.ps1"
}

Invoke-LoggedCommand "mobile cloud sync verification" {
  & $Python ".\verify_mobile_sync.py"
}

Invoke-LoggedCommand "file integrity check" {
  & $Python ".\system_file_check.py"
}

Invoke-LoggedCommand "daily iron-rule audit" {
  & $Python ".\daily_integrity_audit.py"
}

Write-OneClickStatus "passed" "complete" "All one-click steps passed."
Write-RunLog "TW539 one click full run finished."

$ReportPath = Join-Path $ReportDir "latest_battle_report.html"
if ((-not $NoOpen) -and (Test-Path -LiteralPath $ReportPath)) {
  Start-Process $ReportPath
}
