$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ReportDir = Join-Path $ScriptDir "reports"
$StatusPath = Join-Path $ReportDir "daily_auto_task_status.json"
$Runner = Join-Path $ScriptDir "main_one_click.ps1"
$TaskAfterDraw = "TW539 " + (-join ([char[]](0x6BCF,0x65E5,0x958B,0x734E,0x5F8C,0x5168,0x81EA,0x52D5,0x66F4,0x65B0)))
$TaskMidnight = "TW539 " + (-join ([char[]](0x6BCF,0x65E5,0x51CC,0x6668,0x5B8C,0x6574,0x6AA2,0x6E2C)))

New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null

function New-Status {
  return [ordered]@{
    status = "checking"
    written_at = (Get-Date -Format "s")
    runner = $Runner
    startup_tasks_removed = @()
    startup_tasks_failed = @()
    daily_tasks = @()
    rule = "20:45 after-draw update and 00:05 full integrity recompute must exist; boot and logon startup runs must be removed."
  }
}

function Save-Status {
  param($Status)
  $Status.written_at = Get-Date -Format "s"
  $Status | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $StatusPath -Encoding UTF8
}

function Get-TaskTriggerText {
  param($Task)
  try {
    return (($Task.Triggers | ForEach-Object { $_.CimClass.CimClassName }) -join ",")
  } catch {
    return ""
  }
}

function Remove-StartupTask {
  param(
    [string]$TaskName,
    $Status
  )
  try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
    $Status.startup_tasks_removed += $TaskName
    return
  } catch {
  }
  try {
    & schtasks.exe /Delete /TN $TaskName /F *> $null
    if ($LASTEXITCODE -eq 0) {
      $Status.startup_tasks_removed += $TaskName
    } else {
      $Status.startup_tasks_failed += @{
        task = $TaskName
        reason = "delete_exit_code_$LASTEXITCODE"
      }
    }
  } catch {
    $Status.startup_tasks_failed += @{
      task = $TaskName
      reason = $_.Exception.Message
    }
  }
}

function Ensure-DailyTask {
  param(
    [string]$TaskName,
    [string]$At,
    $Status
  )
  $exitCode = 0
  $createMethod = "powershell"
  $nativeError = ""
  try {
    try {
      Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    } catch {
    }
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`" -NoOpen"
    $trigger = New-ScheduledTaskTrigger -Daily -At $At
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
  } catch {
    $createMethod = "schtasks_fallback"
    $nativeError = $_.Exception.Message
    $actionText = '"powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "' + $Runner + '" -NoOpen'
    $args = @("/Create", "/TN", $TaskName, "/SC", "DAILY", "/ST", $At, "/TR", $actionText, "/F")
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & schtasks.exe @args *> $null
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
  }
  $exists = $false
  try {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    $exists = $true
    $triggerText = Get-TaskTriggerText $task
  } catch {
    $triggerText = ""
  }
  $Status.daily_tasks += @{
    task = $TaskName
    time = $At
    create_method = $createMethod
    native_error = $nativeError
    create_exit_code = $exitCode
    exists = $exists
    trigger = $triggerText
    passed = ($exitCode -eq 0 -and $exists)
  }
}

$status = New-Status

if (-not (Test-Path -LiteralPath $Runner)) {
  $status.status = "failed"
  $status.message = "main_one_click.ps1 was not found."
  Save-Status $status
  throw $status.message
}

$knownStartupNames = @(
  "539 Startup Full Run",
  "TW539 Startup Full Run",
  "539 Boot Auto Run",
  "TW539 Boot Auto Run",
  "539 One Click Startup",
  "TW539 One Click Startup",
  ("539 " + (-join ([char[]](0x958B,0x6A5F,0x81EA,0x52D5,0x555F,0x52D5)))),
  ("TW539 " + (-join ([char[]](0x958B,0x6A5F,0x81EA,0x52D5,0x555F,0x52D5)))),
  ("539" + (-join ([char[]](0x4E00,0x9375,0x5168,0x81EA,0x52D5,0x555F,0x52D5)))),
  ("TW539" + (-join ([char[]](0x4E00,0x9375,0x5168,0x81EA,0x52D5,0x555F,0x52D5))))
)

foreach ($name in $knownStartupNames) {
  try {
    $task = Get-ScheduledTask -TaskName $name -ErrorAction Stop
    if ($task) {
      Remove-StartupTask -TaskName $name -Status $status
    }
  } catch {
  }
}

try {
  $validDailyTasks = @($TaskAfterDraw, $TaskMidnight)
  $obsoleteTw539Tasks = Get-ScheduledTask |
    Where-Object {
      $_.TaskName -like "TW539 *" -and
      ($validDailyTasks -notcontains $_.TaskName)
    }
  foreach ($task in $obsoleteTw539Tasks) {
    Remove-StartupTask -TaskName $task.TaskName -Status $status
  }
} catch {
  $status.startup_tasks_failed += @{
    task = "obsolete_tw539_task_scan"
    reason = $_.Exception.Message
  }
}

try {
  $possibleStartupTasks = Get-ScheduledTask |
    Where-Object {
      ($_.TaskName -like "*539*" -or $_.TaskName -like "*TW539*") -and
      ((Get-TaskTriggerText $_) -match "LogonTrigger|BootTrigger")
    }
  foreach ($task in $possibleStartupTasks) {
    Remove-StartupTask -TaskName $task.TaskName -Status $status
  }
} catch {
  $status.startup_tasks_failed += @{
    task = "startup_task_scan"
    reason = $_.Exception.Message
  }
}

Ensure-DailyTask -TaskName $TaskAfterDraw -At "20:45" -Status $status
Ensure-DailyTask -TaskName $TaskMidnight -At "00:05" -Status $status

$failedDaily = @($status.daily_tasks | Where-Object { -not $_.passed })
if ($failedDaily.Count -gt 0 -or $status.startup_tasks_failed.Count -gt 0) {
  $status.status = "failed"
  $status.message = "Automatic daily tasks are not fully healthy."
  Save-Status $status
  throw $status.message
}

$status.status = "passed"
$status.message = "Daily automatic update tasks are installed and startup tasks are removed."
Save-Status $status
Write-Host "Daily automatic update tasks are healthy."
