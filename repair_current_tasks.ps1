$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepairName = (-join ([char[]](0x6BCF,0x65E5,0x81EA,0x52D5,0x66F4,0x65B0,0x6392,0x7A0B,0x4FEE,0x5FA9))) + ".ps1"
$Repair = Join-Path $ScriptDir $RepairName
if (-not (Test-Path -LiteralPath $Repair)) {
  throw "Daily automatic update schedule repair script was not found."
}

& "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File $Repair
exit $LASTEXITCODE
