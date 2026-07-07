$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $ScriptDir "logs"
$ReportDir = Join-Path $ScriptDir "reports"
$StatusPath = Join-Path $ReportDir "three_hour_sync_check_status.json"
$RunLog = Join-Path $LogDir ("three_hour_sync_check_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null
Set-Location -LiteralPath $ScriptDir

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

function Write-RunLog {
  param([string]$Message)
  $line = (Get-Date -Format "s") + " " + $Message
  Write-Host $line
  Add-Content -LiteralPath $RunLog -Value $line -Encoding UTF8
}

function Save-Status {
  param(
    [string]$Status,
    [string]$Step,
    [string]$Message,
    [array]$Steps
  )
  $payload = [ordered]@{
    status = $Status
    step = $Step
    message = $Message
    checked_at = (Get-Date -Format "s")
    log = $RunLog
    rule = "Every 3 hours: rebuild report, rebuild mobile site, publish mobile cloud, verify computer/mobile sync, run iron-rule audit."
    steps = $Steps
  }
  $payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $StatusPath -Encoding UTF8
}

function Invoke-Step {
  param(
    [string]$Name,
    [scriptblock]$Command,
    [ref]$Steps
  )
  Write-RunLog ("START " + $Name)
  $started = Get-Date
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
    $Steps.Value += @{
      name = $Name
      status = "passed"
      seconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
    }
    Write-RunLog ("PASS " + $Name)
  } catch {
    $ErrorActionPreference = "Stop"
    $Steps.Value += @{
      name = $Name
      status = "failed"
      message = $_.Exception.Message
      seconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
    }
    Write-RunLog ("FAIL " + $Name + " : " + $_.Exception.Message)
    throw
  }
}

$steps = @()
$python = Resolve-Python
Write-RunLog "TW539 three-hour sync check started."
Write-RunLog ("Python=" + $python)

try {
  Invoke-Step "compile check" { & $python -m py_compile ".\battle_report.py" ".\pages_build.py" ".\verify_mobile_sync.py" ".\daily_integrity_audit.py" ".\system_file_check.py" } ([ref]$steps)
  Invoke-Step "latest draw quick update" { & $python ".\update_539.py" "--latest" } ([ref]$steps)
  Invoke-Step "rebuild battle report" { & $python ".\battle_report.py" } ([ref]$steps)
  Invoke-Step "rebuild mobile site" { & $python ".\pages_build.py" } ([ref]$steps)
  try {
    Invoke-Step "publish mobile cloud" { & "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File ".\publish_free_github.ps1" } ([ref]$steps)
  } catch {
    Write-RunLog "AUTO REPAIR publish failed; waiting and retrying once."
    Start-Sleep -Seconds 20
    Invoke-Step "publish mobile cloud retry" { & "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File ".\publish_free_github.ps1" } ([ref]$steps)
  }

  try {
    Invoke-Step "verify computer mobile sync" { & $python ".\verify_mobile_sync.py" } ([ref]$steps)
  } catch {
    Write-RunLog "AUTO REPAIR sync verification failed; rebuilding report, rebuilding mobile site, publishing again, then retrying verification."
    Invoke-Step "auto repair rebuild battle report" { & $python ".\battle_report.py" } ([ref]$steps)
    Invoke-Step "auto repair rebuild mobile site" { & $python ".\pages_build.py" } ([ref]$steps)
    Invoke-Step "auto repair publish mobile cloud" { & "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File ".\publish_free_github.ps1" } ([ref]$steps)
    Invoke-Step "verify computer mobile sync retry" { & $python ".\verify_mobile_sync.py" } ([ref]$steps)
  }

  try {
    Invoke-Step "daily iron-rule audit" { & $python ".\daily_integrity_audit.py" } ([ref]$steps)
  } catch {
    Write-RunLog "AUTO REPAIR audit failed; rebuilding report and mobile site, then retrying audit."
    Invoke-Step "auto repair rebuild report after audit failure" { & $python ".\battle_report.py" } ([ref]$steps)
    Invoke-Step "auto repair rebuild mobile after audit failure" { & $python ".\pages_build.py" } ([ref]$steps)
    Invoke-Step "daily iron-rule audit retry" { & $python ".\daily_integrity_audit.py" } ([ref]$steps)
  }
  Save-Status "passed" "complete" "Three-hour report freshness and mobile sync check passed." $steps
  Write-RunLog "TW539 three-hour sync check finished."
} catch {
  Save-Status "failed" "failed" $_.Exception.Message $steps
  throw
}
