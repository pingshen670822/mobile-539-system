$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $ScriptDir "logs"
$ReportDir = Join-Path $ScriptDir "reports"
$StatusPath = Join-Path $ReportDir "one_click_status.json"
$RunLog = Join-Path $LogDir ("one_click_run_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")

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
  $payload = @{
    status = $Status
    step = $Step
    message = $Message
    written_at = (Get-Date -Format "s")
    log = $RunLog
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
    & $Command 2>&1 | Tee-Object -FilePath $RunLog -Append
    if ($LASTEXITCODE -ne $null -and $LASTEXITCODE -ne 0) {
      throw ("Step exited with code " + $LASTEXITCODE)
    }
    Write-RunLog ("PASS " + $Step)
  } catch {
    Write-RunLog ("FAIL " + $Step + " : " + $_.Exception.Message)
    Write-OneClickStatus "failed" $Step $_.Exception.Message
    throw
  }
}

Set-Location -LiteralPath $ScriptDir
$Python = Resolve-Python
Write-RunLog "TW539 one click full run started."
Write-RunLog ("Python=" + $Python)

Invoke-LoggedCommand "compile check" {
  & $Python -m py_compile ".\update_539.py" ".\analyze_539.py" ".\industrial_engine.py" ".\battle_report.py" ".\pages_build.py" ".\verify_mobile_sync.py" ".\daily_integrity_audit.py" ".\system_file_check.py"
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
if (Test-Path -LiteralPath $ReportPath) {
  Start-Process $ReportPath
}
